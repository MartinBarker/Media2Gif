const puppeteer = require('puppeteer');
const readline = require('readline');
const fs = require('fs');
const path = require('path');

// Load .env from root project directory (parent of giphy_upload_bot)
const rootEnvPath = path.resolve(__dirname, '..', '.env');
require('dotenv').config({ path: rootEnvPath });

// Also load local .env if it exists (will not override existing vars)
require('dotenv').config();

// ============================================================================
// CONFIG FILE PARSER
// ============================================================================

function parseConfigFile(configPath) {
  const config = {};
  if (!fs.existsSync(configPath)) {
    console.error(`Config file not found: ${configPath}`);
    process.exit(1);
  }
  
  const content = fs.readFileSync(configPath, 'utf8');
  let currentSection = null;
  
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    
    // Skip comments and empty lines
    if (!trimmed || trimmed.startsWith('#')) continue;
    
    // Section header
    const sectionMatch = trimmed.match(/^\[(.+)\]$/);
    if (sectionMatch) {
      currentSection = sectionMatch[1];
      if (!config[currentSection]) config[currentSection] = {};
      continue;
    }
    
    // Key = value
    const kvMatch = trimmed.match(/^([^=]+)=(.*)$/);
    if (kvMatch && currentSection) {
      const key = kvMatch[1].trim();
      const value = kvMatch[2].trim();
      config[currentSection][key] = value;
    }
  }
  
  return config;
}

function getConfigValue(config, section, key, defaultValue = null) {
  if (config[section] && config[section][key] !== undefined) {
    return config[section][key];
  }
  return defaultValue;
}

// ============================================================================
// PARSE COMMAND LINE ARGUMENTS
// ============================================================================

let configFile = null;
for (let i = 2; i < process.argv.length; i++) {
  if (process.argv[i] === '--config' && process.argv[i + 1]) {
    configFile = process.argv[i + 1];
    break;
  } else if (process.argv[i].startsWith('--config=')) {
    configFile = process.argv[i].split('=')[1];
    break;
  }
}

// ============================================================================
// CONFIGURATION - Load from config file or use defaults
// ============================================================================

let FOLDER_GIF_DIR = '/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs';
let default_tags = '';
let collectionName = '';
let metadataJsonFilename = 'gifs_metadata.json'; // Default, can be overridden by config
const BATCH_SIZE = 100;

if (configFile) {
  console.log(`Loading config from: ${configFile}`);
  const config = parseConfigFile(configFile);
  
  // Read gif_output folder (with 'output' fallback for backwards compatibility)
  FOLDER_GIF_DIR = getConfigValue(config, 'gif_output', 'folder', null) 
                || getConfigValue(config, 'output', 'folder', FOLDER_GIF_DIR);
  
  // Read giphy_upload settings
  default_tags = getConfigValue(config, 'giphy_upload', 'tags', '');
  collectionName = getConfigValue(config, 'giphy_upload', 'collection_name', '');
  metadataJsonFilename = getConfigValue(config, 'giphy_upload', 'metadata_json', 'gifs_metadata.json');
  
  // Also check movie.title to construct default metadata filename if not explicitly set
  if (metadataJsonFilename === 'gifs_metadata.json') {
    const movieTitle = getConfigValue(config, 'movie', 'title', null);
    if (movieTitle) {
      const titleBasedFilename = `gifs_metadata_${movieTitle}.json`;
      const titleBasedPath = path.join(FOLDER_GIF_DIR, titleBasedFilename);
      if (fs.existsSync(titleBasedPath)) {
        metadataJsonFilename = titleBasedFilename;
        console.log(`  Auto-detected metadata file: ${metadataJsonFilename}`);
      }
    }
  }
  
  console.log(`  GIF folder: ${FOLDER_GIF_DIR}`);
  console.log(`  Metadata JSON: ${metadataJsonFilename}`);
  if (collectionName) console.log(`  Collection: ${collectionName}`);
} else {
  console.log('No config file provided. Use --config <path> to specify one.');
  default_tags = '';
  collectionName = '';
}

// Giphy credentials - check multiple env var names for flexibility
const USERNAME = process.env.GIPHY_USERNAME || process.env.username || process.env.USERNAME || process.env.email || process.env.EMAIL;
const PASSWORD = process.env.GIPHY_PASSWORD || process.env.pword || process.env.PWORD || process.env.password || process.env.PASSWORD;
const LOGIN_URL = 'https://giphy.com/login';
const UPLOAD_URL = 'https://giphy.com/upload';

// Create readline interface for user input
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

// Helper function to wait for Enter key
function waitForEnter(prompt) {
  return new Promise((resolve) => {
    console.log(prompt);
    rl.once('line', () => {
      resolve();
    });
  });
}

// Helper function to extract quote from filename
function extractQuoteFromFilename(filename) {
  // Pattern: Quote[...] in filename
  // Handle both Quote[...] and Quote[] (empty quotes)
  const quoteMatch = filename.match(/Quote\[(.*?)\]/);
  if (quoteMatch && quoteMatch[1] && quoteMatch[1].trim() !== '') {
    let quote = quoteMatch[1].trim();
    // Handle escaped quotes (like I'\''d becomes I'd)
    quote = quote.replace(/\\'/g, "'");
    return quote;
  }
  return null;
}

// Helper function to get GIF files from a folder
function getGifFiles(folderPath) {
  const files = fs.readdirSync(folderPath);
  return files
    .filter(file => file.toLowerCase().endsWith('.gif'))
    .map(file => path.join(folderPath, file));
}

// Sanitize a quote for tagging: remove punctuation (esp. commas), keep full length
function sanitizeQuoteTag(str) {
  if (!str) return '';
  const cleaned = str
    .toLowerCase()
    // remove punctuation except ! and ?
    .replace(/[^\w\s!?]/g, '')
    // explicitly drop commas and periods if any remain
    .replace(/[.,]/g, '')
    .replace(/\s+/g, ' ')    // normalize spaces
    .trim();
  return cleaned;
}

// Helper to safely build an XPath literal from arbitrary text
function toXPathLiteral(str) {
  if (!str.includes("'")) {
    return `'${str}'`;
  }
  return `concat('${str.split("'").join("', \"'\", '")}')`;
}

// Load and save metadata JSON
function loadMetadata(folderPath, jsonFilename = 'gifs_metadata.json') {
  const metadataPath = path.join(folderPath, jsonFilename);
  try {
    const raw = fs.readFileSync(metadataPath, 'utf8');
    console.log(`Loaded metadata from: ${metadataPath}`);
    return JSON.parse(raw);
  } catch (e) {
    console.warn(`Could not load ${jsonFilename}: ${e.message}`);
    // Try fallback to default gifs_metadata.json if custom file not found
    if (jsonFilename !== 'gifs_metadata.json') {
      const fallbackPath = path.join(folderPath, 'gifs_metadata.json');
      try {
        const raw = fs.readFileSync(fallbackPath, 'utf8');
        console.log(`Loaded fallback metadata from: ${fallbackPath}`);
        return JSON.parse(raw);
      } catch (e2) {
        console.warn(`Could not load fallback gifs_metadata.json either`);
      }
    }
    return {};
  }
}

function saveMetadata(folderPath, metadata, jsonFilename = 'gifs_metadata.json') {
  const metadataPath = path.join(folderPath, jsonFilename);
  fs.writeFileSync(metadataPath, JSON.stringify(metadata, null, 2), 'utf8');
}

// Get GIFs that haven't been uploaded yet, sorted in REVERSE order (last gif first)
function getUnuploadedGifs(folderPath, metadata) {
  const files = fs.readdirSync(folderPath);
  const gifFiles = files
    .filter(file => file.toLowerCase().endsWith('.gif'))
    .sort(); // Sort alphabetically/chronologically first
  
  // Filter out already uploaded GIFs
  const unuploaded = gifFiles.filter(filename => {
    const entry = metadata[filename];
    return !entry || !entry.giphy_uploaded;
  });
  
  // Reverse so last gif (end of movie) is first to upload
  return unuploaded.reverse();
}

// Build tags for a GIF: quote, 3 actors, description, generic (in priority order)
function buildTagsForGif(filename, metadata, defaultTags) {
  const entry = metadata[filename] || {};
  const tags = [];
  
  // 1. Quote as tag (highest priority)
  const quote = entry.quote || extractQuoteFromFilename(filename) || '';
  if (quote) {
    const sanitizedQuote = sanitizeQuoteTag(quote);
    if (sanitizedQuote) tags.push(sanitizedQuote);
  }
  
  // 2. Up to 3 actors as tags (second priority)
  const actors = entry.actors || '';
  if (actors) {
    const actorList = actors.split(',').map(a => a.trim().toLowerCase()).filter(a => a);
    // Only take first 3 actors
    for (const actor of actorList.slice(0, 3)) {
      if (!tags.includes(actor)) {
        tags.push(actor);
      }
    }
  }
  
  // 3. Description as tag (third priority)
  const description = entry.description || '';
  if (description) {
    const sanitizedDesc = sanitizeQuoteTag(description);
    if (sanitizedDesc && sanitizedDesc !== tags[0]) { // Avoid duplicate if same as quote
      tags.push(sanitizedDesc);
    }
  }
  
  // 4. Add default/generic tags from config (lowest priority)
  if (defaultTags) {
    const defaultTagList = defaultTags.split(',').map(t => t.trim().toLowerCase()).filter(t => t);
    for (const tag of defaultTagList) {
      if (!tags.includes(tag)) {
        tags.push(tag);
      }
    }
  }
  
  // Giphy has a tag limit, keep to 20
  return [...new Set(tags)].slice(0, 20);
}

// Main function
async function main() {
  console.log("beginning GIPHY upload bot...");
  // Validate folder exists
  if (!fs.existsSync(FOLDER_GIF_DIR)) {
    console.error(`GIF folder not found: ${FOLDER_GIF_DIR}`);
    rl.close();
    return;
  }

  // Load metadata
  let metadata = loadMetadata(FOLDER_GIF_DIR, metadataJsonFilename);
  console.log(`Loaded metadata from ${metadataJsonFilename}`);
  
  // Check if there are any unuploaded GIFs
  let allUnuploaded = getUnuploadedGifs(FOLDER_GIF_DIR, metadata);
  
  if (allUnuploaded.length === 0) {
    console.log('\n✓ All GIFs have already been uploaded!');
    rl.close();
    return;
  }
  
  console.log(`\nFound ${allUnuploaded.length} GIFs not yet uploaded`);
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: null,
    args: ['--start-maximized']
  });

  const page = await browser.newPage();
  
  // Navigate to login page
  console.log(`Navigating to ${LOGIN_URL}...`);
  await page.goto(LOGIN_URL, { waitUntil: 'networkidle2' });

  // Ensure credentials exist
  if (!USERNAME || !PASSWORD) {
    console.error('Missing username or password. Please set GIPHY_USERNAME and GIPHY_PASSWORD in .env');
    await browser.close();
    rl.close();
    return;
  }

  // Fill login form and submit
  console.log('Signing in automatically with .env credentials...');
  await page.waitForSelector('input[name="email"]', { timeout: 15000 });
  await page.type('input[name="email"]', USERNAME, { delay: 20 });
  await page.type('input[name="password"]', PASSWORD, { delay: 20 });

  let loginButton = await page.$('button[type="submit"]');
  if (!loginButton) {
    const xpathButtons = await page.$x("//button[contains(., 'Log In') or contains(., 'Log in')]");
    if (xpathButtons && xpathButtons.length) {
      loginButton = xpathButtons[0];
    }
  }
  if (!loginButton) {
    const xpathSpanButtons = await page.$x("//span[contains(., 'Log In') or contains(., 'Log in')]/parent::button");
    if (xpathSpanButtons && xpathSpanButtons.length) {
      loginButton = xpathSpanButtons[0];
    }
  }
  if (loginButton) {
    await loginButton.click();
  } else {
    console.log('Login button not found automatically, submitting via Enter key.');
    await page.keyboard.press('Enter');
  }

  await Promise.race([
    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 20000 }).catch(() => null),
    page.waitForTimeout(5000)
  ]);

  if (page.url().includes('/login')) {
    console.warn('Still on login page; check credentials or captcha.');
  } else {
    console.log('Login successful, current URL:', page.url());
  }

  // === MAIN BATCH UPLOAD LOOP ===
  let batchNumber = 0;
  while (true) {
    batchNumber++;
    
    // Reload metadata to check for remaining unuploaded GIFs
    metadata = loadMetadata(FOLDER_GIF_DIR, metadataJsonFilename);
    allUnuploaded = getUnuploadedGifs(FOLDER_GIF_DIR, metadata);
    
    if (allUnuploaded.length === 0) {
      console.log('\n✓ All GIFs have been uploaded!');
      break;
    }
    
    // Take next batch (up to BATCH_SIZE)
    const batch = allUnuploaded.slice(0, BATCH_SIZE);
    console.log(`\n${'='.repeat(60)}`);
    console.log(`BATCH ${batchNumber}: Processing ${batch.length} GIFs (${allUnuploaded.length} remaining total)`);
    console.log(`First to upload: ${batch[0]}`);
    console.log(`Last to upload: ${batch[batch.length - 1]}`);
    console.log('='.repeat(60));

    // Navigate to upload page
    console.log(`Navigating to ${UPLOAD_URL}...`);
    await page.goto(UPLOAD_URL, { waitUntil: 'networkidle2' });

    // Prepare file paths and metadata for the batch
    const batchFilePaths = batch.map(filename => path.join(FOLDER_GIF_DIR, filename));
    const fileMetadata = batch.map(filename => {
      const tags = buildTagsForGif(filename, metadata, default_tags);
      const gifMeta = metadata[filename] || {};
      const quote = gifMeta.quote || extractQuoteFromFilename(filename) || '';
      return {
        path: path.join(FOLDER_GIF_DIR, filename),
        filename: filename,
        tags: tags,
        description: quote,
        hasQuote: Boolean(quote && quote.trim())
      };
    });

    console.log('\n' + '='.repeat(60));
    console.log(`Uploading batch of ${batch.length} GIFs from: ${FOLDER_GIF_DIR}`);
    console.log('='.repeat(60));

    try {
      // Upload all GIFs via the file input
      console.log('  Locating file input for bulk upload...');
      const fileInput = await page.waitForSelector('input[type="file"][multiple]', { timeout: 15000 });
      await fileInput.uploadFile(...batchFilePaths);
      console.log(`  Submitted ${batch.length} GIFs for upload...`);

      // Ensure at least 30 seconds after submitting files before proceeding
      await page.waitForTimeout(30000);

      // Wait for GIF rows to appear (up to 40s)
      await page.waitForFunction(
        (expected) => document.querySelectorAll('div.Item-sc-glenzl').length >= expected,
        { timeout: 40000 },
        Math.min(batch.length, 100)
      ).catch(() => null);
      
      // Find all GIF rows (accordions) on the page
      const gifRows = await page.$$('div.Item-sc-glenzl');
      console.log(`Found ${gifRows.length} GIF rows (accordions) on page`);
      console.log(`Tagging up to ${Math.min(gifRows.length, fileMetadata.length)} GIFs for this batch`);

      // Add default tags in the "Add Info" section before processing quotes
      try {
        console.log('Adding default tags in Add Info section (before per-GIF quotes)...');
        const addInfoTagsInputHandles = await page.$x("//div[normalize-space(.)=\"Add Info\"]/../..//input[translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='add tags']");
        const addInfoTagsInput = addInfoTagsInputHandles && addInfoTagsInputHandles[0];
        if (addInfoTagsInput && default_tags && default_tags.trim().length > 0) {
          await addInfoTagsInput.click({ clickCount: 3 });
          await page.waitForTimeout(200);
          
          // Type each tag individually with 1 second wait between tags
          const tagList = default_tags.split(',').map(t => t.trim()).filter(t => t);
          for (let i = 0; i < tagList.length; i++) {
            const tag = tagList[i];
            await addInfoTagsInput.type(tag, { delay: 25 });
            console.log(`    Typed tag: ${tag}`);
            await page.waitForTimeout(1000); // Wait 1 second after each tag
            
            // Add comma separator if not the last tag
            if (i < tagList.length - 1) {
              await addInfoTagsInput.type(', ', { delay: 25 });
              await page.waitForTimeout(1000); // Wait 1 second after comma/space
            }
          }
          
          await page.waitForTimeout(300);
          let addBtnHandles = await page.$x("//div[contains(@class,'Title-sc-dtewrf') and contains(., 'Add Info')]/ancestor::div[contains(@class,'GridBlock-sc-15c4h63')]//button[contains(@class,'Button-sc-oi7m9l')]");
          let addBtn = addBtnHandles && addBtnHandles[0];
          if (addBtn) {
            await addBtn.click();
            await page.waitForTimeout(5000);
          } else {
            await page.keyboard.press('Enter');
            await page.waitForTimeout(5000);
          }
          console.log(`  Added default tags: ${default_tags}`);
        } else {
          console.log('  Add Info tags input not found or default_tags empty, skipping.');
        }
      } catch (e) {
        console.log('  Error adding default tags in Add Info:', e.message);
      }
      console.log("Added default tags.")
      // Select collection by name (click collection image)
      try {
        console.log(`Selecting collection: ${collectionName}`);
        let collectionImage = await page.$x(`//div[contains(@class,'Collections-sc-1pr7xpd')]//img[contains(@class,'ItemGif-sc-1q271fd') and ../div[contains(@class,'ItemText')]/a[contains(text(), ${toXPathLiteral(collectionName)})]]`);
        if (!collectionImage || collectionImage.length === 0) {
          const collectionHeader = await page.$x("//div[contains(@class,'Collections-sc-1pr7xpd')]//div[contains(text(),'Add to Collection')]");
          if (collectionHeader && collectionHeader.length) {
            await collectionHeader[0].click();
            await page.waitForTimeout(800);
            collectionImage = await page.$x(`//div[contains(@class,'Collections-sc-1pr7xpd')]//img[contains(@class,'ItemGif-sc-1q271fd') and ../div[contains(@class,'ItemText')]/a[contains(text(), ${toXPathLiteral(collectionName)})]]`);
          }
        }
        if (collectionImage && collectionImage.length) {
          await page.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }), collectionImage[0]);
          await page.waitForTimeout(300);
          await collectionImage[0].click();
          await page.waitForTimeout(800);
          console.log('  Collection selected by image.');
        } else {
          console.log('  Collection not found, skipping selection.');
        }
      } catch (e) {
        console.log('  Error selecting collection:', e.message);
      }

      // Process each GIF's tag field, opening the matching row by filename
      const itemsToProcess = Math.min(gifRows.length, fileMetadata.length);
      for (let i = 0; i < itemsToProcess; i++) {
        const fileMeta = fileMetadata[i];
        console.log(`\n[${i + 1}/${itemsToProcess}] Processing: ${fileMeta.filename}`);
        
        // Check if there are any tags to add (quote, actors, description, or default tags)
        if (!fileMeta.tags || fileMeta.tags.length === 0) {
          console.log('  No tags available for this GIF, skipping tagging/opening.');
          continue;
        }

        try {
          // Find the container that matches this filename by label text
          const literal = toXPathLiteral(fileMeta.filename);
          const rowMatches = await page.$x(
            `//span[contains(@class,"Label-sc-12y1hkg") and normalize-space(text())=${literal}]/ancestor::div[contains(@class,"Container-sc-7cfcqn")]`
          );
          if (!rowMatches || rowMatches.length === 0) {
            console.log('  Could not find row for this filename via label span, skipping.');
            continue;
          }

          const row = rowMatches[0];

          // Scroll row into view (center)
          await page.evaluate((el) => {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, row);
          await page.waitForTimeout(400);

          // Expand/click the row (click the arrow if present) - skip for first item as it's already expanded
          if (i === 0) {
            console.log('  First GIF - already expanded, skipping arrow click.');
          } else {
            console.log('  Expanding row / clicking arrow...');
            let arrow = await row.$('div.ToolButton-sc-3ci5mj, div.ArrowButton-sc-mxmmvb, i.ss-navigatedown');
            if (!arrow) {
              const arrows = await row.$$('div.ToolButton-sc-3ci5mj, div.ArrowButton-sc-mxmmvb, i.ss-navigatedown');
              if (arrows && arrows.length) arrow = arrows[0];
            }
            if (arrow) {
              await arrow.click();
            } else {
              await row.click();
            }
          }
          await page.waitForTimeout(600);

          // Find the tag input inside this row
          console.log('  Locating tag input...');
          let tagInput = await row.$('input[placeholder*="Add tags" i], input.Input-sc-xhq6df');
          if (!tagInput) {
            await page.waitForFunction(
              (el) => !!el.querySelector('input[placeholder*="Add tags" i], input.Input-sc-xhq6df'),
              { timeout: 3000 },
              row
            ).catch(() => null);
            tagInput = await row.$('input[placeholder*="Add tags" i], input.Input-sc-xhq6df');
          }
          if (!tagInput) {
            console.log('  Tag input not found for this GIF, skipping.');
            continue;
          }

          // Scroll tag input to center for visibility
          await page.evaluate((el) => {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, tagInput);
          await page.waitForTimeout(300);

          // Build tags string (quote, description, actors are already in fileMeta.tags via buildTagsForGif)
          const tagsString = fileMeta.tags.join(', ');

          try {
            console.log('  Clicking tag input...');
            await tagInput.click({ clickCount: 3 });
            await page.waitForTimeout(200);

            console.log(`  Typing tags: ${tagsString}`);
            await tagInput.type(tagsString, { delay: 60 });
            await page.waitForTimeout(2000);

            // Find and click the Add Tag button near this input
            console.log('  Attempting to click Add Tag button...');
            let addTagButton = await row.$('button.Button-sc-oi7m9l, button.Button-sc-1dyozow, button:has(svg)');
            if (!addTagButton) {
              const buttons = await row.$$('button');
              if (buttons && buttons.length) {
                addTagButton = buttons.find(async (btn) => {
                  const text = (await (await btn.getProperty('textContent')).jsonValue() || '').toLowerCase();
                  return text.includes('add');
                });
              }
            }

            if (addTagButton && addTagButton.click) {
              await addTagButton.click();
              await page.waitForTimeout(300);
              console.log(`  Added tags: ${tagsString}`);
            } else {
              await page.keyboard.press('Enter');
              await page.waitForTimeout(300);
              console.log(`  Added tags via Enter: ${tagsString}`);
            }
          } catch (tagError) {
            console.log(`  Error adding tags: ${tagError.message}`);
            try {
              await tagInput.click({ clickCount: 3 });
              await page.keyboard.press('Backspace');
              await page.waitForTimeout(80);
            } catch (e) {}
          }
          
          console.log(`  Completed tags for: ${fileMeta.filename}`);
          
        } catch (error) {
          console.error(`Error processing ${fileMeta.filename}:`, error.message);
        }
      }
      
      console.log(`\nFinished adding tags to all GIFs in batch`);

      // Re-select collection before upload
      try {
        console.log(`Re-selecting collection before upload: ${collectionName}`);
        let selected = false;
        const maxAttempts = 10;
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
          let collectionImage = await page.$x(`//div[contains(@class,'Collections-sc-1pr7xpd')]//img[contains(@class,'ItemGif-sc-1q271fd') and ../div[contains(@class,'ItemText')]/a[contains(text(), ${toXPathLiteral(collectionName)})]]`);
          if (!collectionImage || collectionImage.length === 0) {
            const collectionHeader = await page.$x("//div[contains(@class,'Collections-sc-1pr7xpd')]//div[contains(text(),'Add to Collection')]");
            if (collectionHeader && collectionHeader.length) {
              await collectionHeader[0].click();
              await page.waitForTimeout(800);
              collectionImage = await page.$x(`//div[contains(@class,'Collections-sc-1pr7xpd')]//img[contains(@class,'ItemGif-sc-1q271fd') and ../div[contains(@class,'ItemText')]/a[contains(text(), ${toXPathLiteral(collectionName)})]]`);
            }
          }
          if (collectionImage && collectionImage.length) {
            await page.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }), collectionImage[0]);
            await page.waitForTimeout(300);
            await collectionImage[0].click();
            await page.waitForTimeout(800);
            const addingText = await page.$x("//div[contains(@class,'ElipisisOverflow-sc-1635sfj') and contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'adding to')]");
            if (addingText && addingText.length) {
              console.log('  Collection selected by image (pre-upload) and confirmation text found.');
              selected = true;
              break;
            }
          }
          console.log(`  Collection not confirmed yet (attempt ${attempt}/${maxAttempts}), retrying...`);
          await page.waitForTimeout(2000);
        }
        if (!selected) {
          console.log('  Collection not confirmed before upload, proceeding without re-selecting.');
        }
      } catch (e) {
        console.log('  Error re-selecting collection before upload:', e.message);
      }

      // Click Upload to GIPHY button
      try {
        console.log('Clicking Upload to GIPHY...');
        const agreeBtn = await page.$('#didomi-notice-agree-button');
        if (agreeBtn) {
          console.log('  Found Agree button, clicking...');
          await agreeBtn.click();
          await page.waitForTimeout(3000);
        }

        const uploadBtn = await page.$x("//div[contains(@class,'Button-sc-fko3q9') and contains(., 'Upload to GIPHY')]");
        if (uploadBtn && uploadBtn.length) {
          await uploadBtn[0].click();
          console.log('Waiting for uploads to finish (progress text or Open Channel)...');
          
          const MIN_WAIT_MS = 5 * 60 * 1000;
          const startWait = Date.now();

          const waitForProgressOrOpen = async () => {
            try {
              await Promise.race([
                page.waitForFunction(
                  () => {
                    const open = document.querySelector('a.GradientBlock-sc-mtbfu0.GradientButton-sc-o939k5.Button-sc-fko3q9[href*="channel"]');
                    if (open) return true;
                    const progress = Array.from(document.querySelectorAll('span')).some(s => /Uploading\s+\d+\s+of\s+\d+/i.test(s.textContent || ''));
                    return progress;
                  },
                  { timeout: MIN_WAIT_MS }
                ).catch(() => null),
                page.waitForTimeout(MIN_WAIT_MS)
              ]);
            } catch (e) {}
          };

          await waitForProgressOrOpen();

          const remainingWait = Math.max(0, MIN_WAIT_MS - (Date.now() - startWait));
          if (remainingWait > 0) {
            await page.waitForTimeout(remainingWait);
          }

          await Promise.race([
            page.waitForFunction(
              () => !!document.querySelector('a.GradientBlock-sc-mtbfu0.GradientButton-sc-o939k5.Button-sc-fko3q9[href*="channel"]'),
              { timeout: 180000 }
            ).catch(() => null),
            page.waitForFunction(
              () => !Array.from(document.querySelectorAll('span')).some(s => /Uploading\s+\d+\s+of\s+\d+/i.test(s.textContent || '')),
              { timeout: 180000 }
            ).catch(() => null),
            page.waitForTimeout(180000)
          ]);

          console.log('Upload sequence finished.');
          
          // Mark all GIFs in this batch as uploaded
          console.log('Marking batch as uploaded in metadata...');
          for (const filename of batch) {
            if (!metadata[filename]) {
              metadata[filename] = {};
            }
            metadata[filename].giphy_uploaded = true;
          }
          saveMetadata(FOLDER_GIF_DIR, metadata, metadataJsonFilename);
          console.log(`Marked ${batch.length} GIFs as giphy_uploaded: true`);
          
          console.log(`\nBatch ${batchNumber} complete! Uploaded ${batch.length} GIFs.`);
          
          // Check if there are more batches to upload
          metadata = loadMetadata(FOLDER_GIF_DIR, metadataJsonFilename);
          allUnuploaded = getUnuploadedGifs(FOLDER_GIF_DIR, metadata);
          
          if (allUnuploaded.length === 0) {
            console.log('\n✓ All GIFs uploaded! No more batches remaining.');
            break;
          } else {
            // Cooldown before next batch
            const waitMinutes = 15;
            for (let m = waitMinutes; m > 0; m--) {
              console.log(`Waiting for cooldown: ${m} minute(s) remaining...`);
              await page.waitForTimeout(60_000);
            }
            console.log('Cooldown complete. Proceeding to next batch...\n');
          }
        } else {
          console.log('  Upload button not found.');
          break;
        }
      } catch (e) {
        console.log('  Error clicking Upload to GIPHY:', e.message);
        break;
      }
      
    } catch (error) {
      console.error(`Error uploading batch ${batchNumber}:`, error.message);
      break;
    }
  }

  await browser.close();
  rl.close();
}

// Run the main function
main().catch(error => {
  console.error('Error:', error);
  rl.close();
  process.exit(1);
});

