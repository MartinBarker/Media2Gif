const puppeteer = require('puppeteer');
const readline = require('readline');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

// Configuration
const FOLDER_GIF_DIR = '/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs';
// Hardcoded list of subfolder paths to process, in order
const SUBFOLDER_PATHS = [
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_001",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_002",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_003",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_004",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_005",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_006",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_007",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_008",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_009",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_010",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_011",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_012",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_013",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_014",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_015",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_016",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_017",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_018",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_019",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_020",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_021",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_022",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_023",
  "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs/batch_024"
];

const default_tags = 'avatar,avatar 2,avatar the way of water,avatar way of water,avatar 2022,james cameron,sam worthington,zoe saldana,sigourney weaver,stephen lang,kate winslet,cliff curtis,joel david moore,edie falco,brendan cowell,jemaine clement,giovanni ribisi,movie,sci fi,fantasy,action,adventure,na vi,pandora';
//const default_tags=''

const collectionName = "Avatar: The Way of Water 2022 full movie";

const USERNAME = process.env.username || process.env.USERNAME || process.env.email || process.env.EMAIL;
const PASSWORD = process.env.pword || process.env.PWORD || process.env.password || process.env.PASSWORD;
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

// Helper function to get subfolders sorted
function getSubfolders(dir) {
  const items = fs.readdirSync(dir, { withFileTypes: true });
  return items
    .filter(item => item.isDirectory() && item.name.startsWith('batch_'))
    .map(item => item.name)
    .sort();
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

// Main function
async function main() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: null,
    args: ['--start-maximized']
  });

  const page = await browser.newPage();
  
  // Load metadata quotes map
  let quotesMap = {};
  const metadataPath = path.join(FOLDER_GIF_DIR, 'gifs_metadata.json');
  try {
    const raw = fs.readFileSync(metadataPath, 'utf8');
    quotesMap = JSON.parse(raw);
    console.log('Loaded gifs_metadata.json for full quotes');
  } catch (e) {
    console.warn('Could not load gifs_metadata.json, falling back to filename quotes.');
  }
  
  // Navigate to login page
  console.log(`Navigating to ${LOGIN_URL}...`);
  await page.goto(LOGIN_URL, { waitUntil: 'networkidle2' });

  // Ensure credentials exist
  if (!USERNAME || !PASSWORD) {
    console.error('Missing username or password. Please set username and pword in .env');
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

  // Get first subfolder
    // Use explicit list of subfolder paths
    let subfolders = SUBFOLDER_PATHS;
  if (subfolders.length === 0) {
    console.log('No batch folders found!');
    await browser.close();
    rl.close();
    return;
  }

  // Navigate to upload page
  console.log(`Navigating to ${UPLOAD_URL}...`);
  await page.goto(UPLOAD_URL, { waitUntil: 'networkidle2' });

  // Process each subfolder
    for (const folderPath of subfolders) {
    const gifFiles = getGifFiles(folderPath);
    
    if (gifFiles.length === 0) {
      console.log(`\nNo GIF files in ${subfolder}, skipping...`);
      continue;
    }

    // CHECKPOINT: Show which folder to upload
    console.log('\n' + '='.repeat(60));
    console.log(`Uploading folder: ${folderPath}`);
    console.log(`Files in folder: ${gifFiles.length}`);
    console.log('='.repeat(60));

    // Get files to process (limit to 100) for metadata extraction
    const filesToProcess = gifFiles.slice(0, 100);
    
    // Prepare file metadata for each file (prefer full quote from metadata JSON)
    const fileMetadata = filesToProcess.map(gifPath => {
      const filename = path.basename(gifPath);
      // Prefer JSON quote if available; fallback to filename quote
      let quote = '';
      if (quotesMap[filename] && typeof quotesMap[filename].quote === 'string') {
        quote = quotesMap[filename].quote || '';
      } else {
        quote = extractQuoteFromFilename(filename) || '';
      }
      const hasQuote = Boolean(quote && quote.trim());
      
      // Prepare tags (only the full quote as a single sanitized tag; no default tags, no per-word tags)
      let tags = [];
      if (quote) {
        const fullQuoteTag = sanitizeQuoteTag(quote);
        if (fullQuoteTag.length > 0) {
          tags.push(fullQuoteTag);
        }
      }
      // Deduplicate tags to avoid re-adding the same tag
      tags = [...new Set(tags)].slice(0, 20); // enforce max 20 tags per upload (though we expect at most 1)
      
      // Prepare description
      const description = quote || '';
      
      return {
        path: gifPath,
        filename: filename,
        tags: tags,
        description: description,
        hasQuote
      };
    });

    try {
      // Upload all GIFs in this folder via the file input
      console.log('  Locating file input for bulk upload...');
      const fileInput = await page.waitForSelector('input[type="file"][multiple]', { timeout: 15000 });
      await fileInput.uploadFile(...gifFiles);
      console.log(`  Submitted ${gifFiles.length} GIFs for upload...`);

      // Ensure at least 30 seconds after submitting files before proceeding
      await page.waitForTimeout(30000);

      // Wait for GIF rows to appear (up to 40s)
      await page.waitForFunction(
        (expected) => document.querySelectorAll('div.Item-sc-glenzl').length >= expected,
        { timeout: 40000 },
        Math.min(gifFiles.length, 100)
      ).catch(() => null);
      
      // Find all GIF rows (accordions) on the page
      const gifRows = await page.$$('div.Item-sc-glenzl');
      console.log(`Found ${gifRows.length} GIF rows (accordions) on page`);
      console.log(`Tagging up to ${Math.min(gifRows.length, fileMetadata.length)} GIFs for this batch`);

      // Add default tags in the "Add Info" section before processing quotes
      try {
        console.log('Adding default tags in Add Info section (before per-GIF quotes)...');
        // Use explicit XPath provided to target Add Info tags input
        const addInfoTagsInputHandles = await page.$x("//div[normalize-space(.)=\"Add Info\"]/../..//input[translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='add tags']");
        const addInfoTagsInput = addInfoTagsInputHandles && addInfoTagsInputHandles[0];
        if (addInfoTagsInput && default_tags && default_tags.trim().length > 0) {
          await addInfoTagsInput.click({ clickCount: 3 });
          await page.waitForTimeout(200);
          await addInfoTagsInput.type(default_tags, { delay: 25 });
          await page.waitForTimeout(300);
          // Add button within the same Add Info block
          let addBtnHandles = await page.$x("//div[contains(@class,'Title-sc-dtewrf') and contains(., 'Add Info')]/ancestor::div[contains(@class,'GridBlock-sc-15c4h63')]//button[contains(@class,'Button-sc-oi7m9l')]");
          let addBtn = addBtnHandles && addBtnHandles[0];
          if (addBtn) {
            await addBtn.click();
            await page.waitForTimeout(5000); // wait 5s after adding
          } else {
            await page.keyboard.press('Enter');
            await page.waitForTimeout(5000); // wait 5s after adding
          }
          console.log(`  Added default tags: ${default_tags}`);
        } else {
          console.log('  Add Info tags input not found or default_tags empty, skipping.');
        }
      } catch (e) {
        console.log('  Error adding default tags in Add Info:', e.message);
      }

      // Select collection by name (click collection image)
      try {
        console.log(`Selecting collection: ${collectionName}`);
        // Attempt to find the collection image whose adjacent text matches the collection name
        let collectionImage = await page.$x(`//div[contains(@class,'Collections-sc-1pr7xpd')]//img[contains(@class,'ItemGif-sc-1q271fd') and ../div[contains(@class,'ItemText')]/a[contains(text(), ${toXPathLiteral(collectionName)})]]`);
        // If not visible, try clicking the Add to Collection header to expand, then retry
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
        const metadata = fileMetadata[i];
        console.log(`\n[${i + 1}/${itemsToProcess}] Processing: ${metadata.filename}`);
        
        // Skip GIFs without quotes; don't open their sections
        if (!metadata.hasQuote) {
          console.log('  No quote found for this GIF, skipping tagging/opening.');
          continue;
        }

        try {
          // Find the container that matches this filename by label text
          const literal = toXPathLiteral(metadata.filename);
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

          // Expand/click the row (click the arrow if present) for every item
          console.log('  Expanding row / clicking arrow...');
          let arrow = await row.$('div.ToolButton-sc-3ci5mj, div.ArrowButton-sc-mxmmvb, i.ss-navigatedown');
          if (!arrow) {
            const arrows = await row.$$('div.ToolButton-sc-3ci5mj, div.ArrowButton-sc-mxmmvb, i.ss-navigatedown');
            if (arrows && arrows.length) arrow = arrows[0];
          }
          if (arrow) {
            await arrow.click();
          } else {
            await row.click(); // fallback
          }
          await page.waitForTimeout(600);

          // Find the tag input inside this row
          console.log('  Locating tag input...');
          let tagInput = await row.$('input[placeholder*="Add tags" i], input.Input-sc-xhq6df');
          if (!tagInput) {
            // Try waiting until the input appears inside this row
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

          // Prepare all tags to add (default tags + quote words + full quote), already deduped
          const allTags = [...metadata.tags];
          const tagsString = allTags.join(', ');

          try {
            console.log('  Clicking tag input...');
            await tagInput.click({ clickCount: 3 });
            await page.waitForTimeout(200);

            // Type all tags (single sanitized quote) a bit slower
            console.log(`  Typing tags: ${tagsString}`);
            await tagInput.type(tagsString, { delay: 60 });
            await page.waitForTimeout(2000); // wait 2s after finishing typing

            // Find and click the Add Tag button near this input
            console.log('  Attempting to click Add Tag button...');
            let addTagButton = await row.$('button.Button-sc-oi7m9l, button.Button-sc-1dyozow, button:has(svg)');
            if (!addTagButton) {
              // fallback: search within the row for any button next to input
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
              // fallback: press Enter once
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
          
          console.log(`  Completed tags for: ${metadata.filename}`);
          
        } catch (error) {
          console.error(`Error processing ${metadata.filename}:`, error.message);
          // Continue with next file
        }
      }
      
      console.log(`\nFinished adding tags to all GIFs in ${folderPath}`);

      // Select collection by name
      try {
        console.log(`Selecting collection: ${collectionName}`);
        // Attempt to find the collection image whose adjacent text matches the collection name
        let collectionImage = await page.$x(`//div[contains(@class,'Collections-sc-1pr7xpd')]//img[contains(@class,'ItemGif-sc-1q271fd') and ../div[contains(@class,'ItemText')]/a[contains(text(), ${toXPathLiteral(collectionName)})]]`);
        // If not visible, try clicking the Add to Collection header to expand, then retry
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

      // Click Upload to GIPHY button
      try {
        // Ensure collection is selected just before upload (click the image by collection name)
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
              // Check for the "Adding to <collection>" text
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

        console.log('Clicking Upload to GIPHY...');
        // If consent/agree button is present and blocking, click it first
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
          // Enforce minimum 5-minute wait while also checking for completion
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
            } catch (e) {
              // ignore
            }
          };

          await waitForProgressOrOpen();

          const remainingWait = Math.max(0, MIN_WAIT_MS - (Date.now() - startWait));
          if (remainingWait > 0) {
            await page.waitForTimeout(remainingWait);
          }

          // After minimum wait, continue waiting until Open Channel appears or progress text disappears (additional grace up to 3 minutes)
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

          console.log('Upload sequence finished (minimum wait elapsed and completion detected or grace period expired).');
          
          // After uploads, wait 15 minutes with status every minute, then prompt user to continue
          const waitMinutes = 15;
          for (let m = waitMinutes; m > 0; m--) {
            console.log(`Waiting for cooldown: ${m} minute(s) remaining before prompt...`);
            await page.waitForTimeout(60_000);
          }
          console.log('Cooldown complete. Proceeding to next folder.');
        } else {
          console.log('  Upload button not found.');
        }
      } catch (e) {
        console.log('  Error clicking Upload to GIPHY:', e.message);
      }
      
      
    } catch (error) {
      console.error(`Error uploading files:`, error.message);
    }
    
    console.log(`\nCompleted processing folder: ${folderPath}`);
  }

  console.log('\nAll folders processed!');
  await browser.close();
  rl.close();
  return;
}

// Run the main function
main().catch(error => {
  console.error('Error:', error);
  rl.close();
  process.exit(1);
});

