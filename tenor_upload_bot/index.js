const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const readline = require('readline');
require('dotenv').config();

// Configuration
const SUBFOLDER_PATHS = [
  "/mnt/q/movies/Heat (1995) [1080p]/entire_movie_gifs/batch_012",
  "/mnt/q/movies/Heat (1995) [1080p]/entire_movie_gifs/batch_013",
  "/mnt/q/movies/Heat (1995) [1080p]/entire_movie_gifs/batch_014"
];
const UPLOAD_LOG_PATH = path.join(__dirname, 'uploaded.json');
const MAX_FILES_PER_BATCH = 10;
const LOGIN_URL = 'https://tenor.com/';
const GIF_MAKER_URL = 'https://tenor.com/gif-maker?utm_source=nav-bar&utm_medium=internal&utm_campaign=gif-maker-entrypoints';

// Readline for user prompts
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});
const waitForEnter = (prompt) => new Promise((resolve) => {
  console.log(prompt);
  rl.once('line', resolve);
});

// Upload log helpers
function loadUploadLog() {
  try {
    if (fs.existsSync(UPLOAD_LOG_PATH)) {
      return JSON.parse(fs.readFileSync(UPLOAD_LOG_PATH, 'utf8'));
    }
  } catch (e) {
    console.warn('Could not load upload log, starting fresh:', e.message);
  }
  return {};
}
function saveUploadLog(log) {
  fs.writeFileSync(UPLOAD_LOG_PATH, JSON.stringify(log, null, 2));
}

// Helper: extract quote from filename pattern Quote[...]
function extractQuote(filename) {
  const m = filename.match(/Quote\[(.*?)\]/);
  if (m && m[1] != null) {
    return m[1].trim();
  }
  return '';
}

// Prepare tags string from quote (simple: sanitized words)
function tagsFromQuote(quote) {
  if (!quote) return '';
  const cleaned = quote
    .replace(/[^\w\s!?]/g, '')
    .replace(/[.,]/g, '')
    .trim();
  if (!cleaned) return '';
  return cleaned;
}

async function main() {
  const uploadLog = loadUploadLog();

  console.log('Launching browser...');
  const browser = await puppeteer.launch({ headless: false, defaultViewport: null, args: ['--start-maximized'] });
  const page = await browser.newPage();

  // Login page
  console.log(`Navigating to ${LOGIN_URL}...`);
  await page.goto(LOGIN_URL, { waitUntil: 'networkidle2' });
  await waitForEnter('Sign in manually, then press Enter to continue...');

  // Go to GIF maker
  console.log(`Navigating to ${GIF_MAKER_URL}...`);
  await page.goto(GIF_MAKER_URL, { waitUntil: 'networkidle2' });

  for (const folderPath of SUBFOLDER_PATHS) {
    let files = [];
    try {
      files = fs.readdirSync(folderPath)
        .filter((f) => f.toLowerCase().endsWith('.gif'))
        .map((f) => path.join(folderPath, f));
    } catch (e) {
      console.log(`Folder not readable ${folderPath}: ${e.message}`);
      continue;
    }
    // Skip already uploaded
    files = files.filter((f) => !uploadLog[f]);
    if (files.length === 0) {
      console.log(`No new GIFs in ${folderPath}, skipping.`);
      continue;
    }
    // Process in batches of MAX_FILES_PER_BATCH
    for (let i = 0; i < files.length; i += MAX_FILES_PER_BATCH) {
      const batchFiles = files.slice(i, i + MAX_FILES_PER_BATCH);
      console.log(`Uploading batch ${i / MAX_FILES_PER_BATCH + 1}: ${batchFiles.length} files from ${folderPath}`);

      // Wait for file input
      const fileInput = await page.waitForSelector('input[type="file"][multiple]', { timeout: 20000 });
      await fileInput.uploadFile(...batchFiles);
      console.log('Files selected, waiting for queue items to render...');

      // Wait for queue items to appear
      await page.waitForFunction(
        (expected) => document.querySelectorAll('.tagging-queue .queue-item').length >= expected,
        { timeout: 30000 },
        batchFiles.length
      ).catch(() => null);

      // Add tags per queue item
      for (let idx = 0; idx < batchFiles.length; idx++) {
        const filename = path.basename(batchFiles[idx]);
        const quote = extractQuote(filename);
        const tags = tagsFromQuote(quote);
        if (!tags) {
          console.log(`  [${idx + 1}] No quote tags for ${filename}, skipping tag input.`);
          continue;
        }
        const inputId = `#upload_tags_${idx}`;
        try {
          const tagInput = await page.$(inputId);
          if (tagInput) {
            await tagInput.click({ clickCount: 3 });
            await page.waitForTimeout(150);
            await tagInput.type(tags, { delay: 40 });
            await page.waitForTimeout(200);
            console.log(`  [${idx + 1}] Added tags for ${filename}: ${tags}`);
          } else {
            console.log(`  [${idx + 1}] Tag input not found for ${filename}`);
          }
        } catch (e) {
          console.log(`  [${idx + 1}] Error adding tags for ${filename}: ${e.message}`);
        }
      }

      // Click Upload to Tenor and wait for user confirmation
      try {
        const uploadBtn = await page.$x("//button[contains(., 'Upload To Tenor')]");
        if (uploadBtn && uploadBtn.length) {
          await uploadBtn[0].click();
          console.log('Clicked Upload To Tenor for this batch.');
        } else {
          console.log('Upload button not found for this batch.');
        }
      } catch (e) {
        console.log('Error clicking Upload To Tenor:', e.message);
      }

      await waitForEnter('Press Enter after this batch is done processing to continue...');

      // Mark uploaded
      batchFiles.forEach((f) => { uploadLog[f] = true; });
      saveUploadLog(uploadLog);
      console.log('Batch logged as uploaded.');
    }
  }

  console.log('All subfolders processed.');
  await browser.close();
  rl.close();
}

main().catch((err) => {
  console.error('Fatal error:', err);
  rl.close();
  process.exit(1);
});

