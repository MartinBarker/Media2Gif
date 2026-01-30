#!/usr/bin/env bash
# Script to generate GIFs, organize them into batches, and upload to Giphy

set -e  # Exit on error

# Configuration - Edit these paths as needed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOVIE_PATH="/mnt/q/movies/Heat (1995) [1080p]/Heat.1995.1080p.BRrip.x264.YIFY.mp4"
SUBTITLE_PATH="/mnt/q/movies/Heat (1995) [1080p]/Heat.1995.1080p.BRrip.x264.YIFY.srt"
OUTPUT_FOLDER="entire_movie_gifs"

# Get collection name from user
if [ -z "$1" ]; then
    echo "Usage: $0 <giphy_collection_name>"
    echo "Example: $0 'Heat 1995 Full Movie'"
    exit 1
fi

COLLECTION_NAME="$1"

# Calculate output directory (relative to movie directory)
MOVIE_DIR="$(dirname "$MOVIE_PATH")"
OUTPUT_DIR="$MOVIE_DIR/$OUTPUT_FOLDER"

echo "=========================================="
echo "GIF Generation and Upload Script"
echo "=========================================="
echo "Movie: $MOVIE_PATH"
echo "Subtitles: $SUBTITLE_PATH"
echo "Output Directory: $OUTPUT_DIR"
echo "Giphy Collection: $COLLECTION_NAME"
echo "=========================================="
echo ""

# Step 1: Generate GIFs
echo "Step 1: Generating GIFs..."
echo "----------------------------------------"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

python make_gifs.py \
    --movie "$MOVIE_PATH" \
    --subtitles "$SUBTITLE_PATH" \
    --outputFolder "$OUTPUT_FOLDER" \
    --maxFilesize "15mb" \
    --quotes true \
    --saveJson \
    --subtitleColor "white" \
    --subtitleSize 35 \
    --textBorder 3 \
    --textPadding 15 \
    --bottomPadding 20 \
    --uppercase

if [ $? -ne 0 ]; then
    echo "Error: GIF generation failed!"
    exit 1
fi

echo ""
echo "Step 1 complete: GIFs generated successfully!"
echo ""

# Step 2: Organize GIFs into batches of 100
echo "Step 2: Organizing GIFs into batches of 100..."
echo "----------------------------------------"

if [ ! -f "$OUTPUT_DIR/100folders.sh" ]; then
    echo "Error: 100folders.sh not found in $OUTPUT_DIR"
    exit 1
fi

cd "$OUTPUT_DIR"
bash 100folders.sh "$OUTPUT_DIR"

if [ $? -ne 0 ]; then
    echo "Error: Organizing GIFs into batches failed!"
    exit 1
fi

echo ""
echo "Step 2 complete: GIFs organized into batches!"
echo ""

# Step 3: Upload to Giphy
echo "Step 3: Uploading GIFs to Giphy..."
echo "----------------------------------------"

GIPHY_BOT_DIR="$OUTPUT_DIR/giphy upload bot"

if [ ! -d "$GIPHY_BOT_DIR" ]; then
    echo "Error: Giphy upload bot directory not found: $GIPHY_BOT_DIR"
    exit 1
fi

cd "$GIPHY_BOT_DIR"

# Check if node_modules exists, if not, run npm install
if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install
fi

# Modify the index.js to use the provided collection name and output directory
# Create a temporary copy of index.js with modifications
TEMP_INDEX_JS="index_temp_$$.js"
cp index.js "$TEMP_INDEX_JS"

# Update collectionName
sed -i "s/const collectionName = \".*\";/const collectionName = \"$COLLECTION_NAME\";/" "$TEMP_INDEX_JS"

# Update FOLDER_GIF_DIR to use the actual output directory
sed -i "s|const FOLDER_GIF_DIR = '.*';|const FOLDER_GIF_DIR = '$OUTPUT_DIR';|" "$TEMP_INDEX_JS"

# Update SUBFOLDER_PATHS to dynamically find all batch folders
# Find all batch folders and create the array
BATCH_FOLDERS=$(find "$OUTPUT_DIR" -maxdepth 1 -type d -name "batch_*" | sort)
BATCH_ARRAY="["
FIRST=true
while IFS= read -r folder; do
    if [ -n "$folder" ]; then
        if [ "$FIRST" = true ]; then
            BATCH_ARRAY="$BATCH_ARRAY\n  \"$folder\""
            FIRST=false
        else
            BATCH_ARRAY="$BATCH_ARRAY,\n  \"$folder\""
        fi
    fi
done <<< "$BATCH_FOLDERS"
BATCH_ARRAY="$BATCH_ARRAY\n];"

# Use a Node.js script to replace the SUBFOLDER_PATHS array
node << EOF
const fs = require('fs');
const path = require('path');

const filePath = '$TEMP_INDEX_JS';
let content = fs.readFileSync(filePath, 'utf8');

// Find all batch folders
const { execSync } = require('child_process');
const outputDir = '$OUTPUT_DIR';
const batchFolders = execSync(\`find "\${outputDir}" -maxdepth 1 -type d -name "batch_*" | sort\`, { encoding: 'utf8' })
    .trim()
    .split('\\n')
    .filter(f => f.trim());

// Create the array string
const batchArray = 'const SUBFOLDER_PATHS = [\\n' + 
    batchFolders.map(f => \`  "\${f}"\`).join(',\\n') + 
    '\\n];';

// Replace the SUBFOLDER_PATHS array (match multiline)
const pattern = /const SUBFOLDER_PATHS = \\[[\\s\\S]*?\\];/;
content = content.replace(pattern, batchArray);

fs.writeFileSync(filePath, content, 'utf8');
console.log(\`Updated SUBFOLDER_PATHS with \${batchFolders.length} batch folders\`);
EOF

# Run the modified script
echo "Starting Giphy upload bot with collection: $COLLECTION_NAME"
node "$TEMP_INDEX_JS"

# Clean up temporary file
rm -f "$TEMP_INDEX_JS"

echo ""
echo "Step 3 complete: Upload process finished!"
echo ""

echo "=========================================="
echo "All steps completed successfully!"
echo "=========================================="

