#!/usr/bin/env bash
# Group GIFs into sequential folders of 100, preserving name order.
#
# Usage:
#   ./100folders.sh [path_to_gif_folder]
#
# Examples:
#   # Organize GIFs in the current directory
#   ./100folders.sh
#
#   # Organize GIFs in a specific directory
#   ./100folders.sh "/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/entire_movie_gifs"
#
#   # Organize GIFs using a relative path
#   ./100folders.sh "./gif_output"
#
# Description:
#   This script finds all .gif files in the specified directory (or current directory if none specified)
#   and organizes them into sequential folders named batch_001, batch_002, etc., with up to 100 GIFs per folder.
#   GIFs are sorted alphabetically before being moved into batches.

BATCH_SIZE=100
prefix="batch"
gif_dir="${1:-.}"

if [[ ! -d "$gif_dir" ]]; then
  echo "Directory not found: $gif_dir"
  exit 1
fi

echo "Target directory: $gif_dir"

# Change to the target directory to ensure we're working in the right place
cd "$gif_dir" || exit 1

batch_idx=1
item_in_batch=0
folder=""
processed=0

echo "Scanning for GIFs..."

# Find all GIF files in current directory only (not in subdirectories)
# Sort them and process one by one
while IFS= read -r -d '' gif; do
  # Skip if file doesn't exist (might have been moved already)
  [[ ! -f "$gif" ]] && continue
  
  # Start new batch folder when needed
  if (( item_in_batch == 0 )); then
    folder=$(printf "%s_%03d" "$prefix" "$batch_idx")
    mkdir -p "$folder"
    echo "Creating folder: $folder"
    ((batch_idx++))
  fi

  # Move the file (suppress errors if file was already moved)
  if mv -- "$gif" "$folder/" 2>/dev/null; then
    echo "  moved $(basename -- "$gif") -> $folder/"
    ((item_in_batch++))
    ((processed++))
    
    # Reset counter when batch is full
    if (( item_in_batch == BATCH_SIZE )); then
      item_in_batch=0
    fi
  else
    echo "  warning: failed to move $(basename -- "$gif")"
  fi
done < <(find . -maxdepth 1 -type f \( -iname '*.gif' \) -print0 | sort -z)

if (( processed == 0 )); then
  echo "No GIFs found or moved in $gif_dir."
  exit 0
fi

echo ""
echo "Done. Moved $processed GIF(s) into $((batch_idx - 1)) folder(s) with up to $BATCH_SIZE GIFs each."