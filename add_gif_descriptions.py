#!/usr/bin/env python3
"""
Add AI-generated descriptions to GIF metadata using a local Ollama vision model.

Prerequisites:
1. Install Ollama: https://ollama.com/download
2. Pull a vision model: ollama pull llava
3. Make sure Ollama is running: ollama serve

Usage:
    python add_gif_descriptions.py --folder "hard_boiled_gifs"
    python add_gif_descriptions.py --folder "hard_boiled_gifs" --model "llava:13b"
    python add_gif_descriptions.py --folder "hard_boiled_gifs" --skip-existing
"""

import os
import json
import base64
import argparse
import requests
from PIL import Image
import io

# Ollama API endpoint (default local)
OLLAMA_API_URL = "http://localhost:11434/api/generate"

def extract_frame_from_gif(gif_path, frame_index=None):
    """Extract a frame from a GIF file and return as base64."""
    try:
        with Image.open(gif_path) as img:
            # Get total number of frames
            n_frames = getattr(img, 'n_frames', 1)
            
            # Use middle frame if no specific frame requested
            if frame_index is None:
                frame_index = n_frames // 2
            
            # Seek to the desired frame
            img.seek(min(frame_index, n_frames - 1))
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Save to bytes buffer
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)
            
            # Return base64 encoded
            return base64.b64encode(buffer.read()).decode('utf-8')
    except Exception as e:
        print(f"Error extracting frame from {gif_path}: {e}")
        return None

def get_description_from_ollama(image_base64, model="llava"):
    """Send image to Ollama vision model and get description."""
    prompt = """Describe what is happening in this image in a short, concise phrase (5-15 words). 
Focus on the main action or scene. Examples of good descriptions:
- "man pointing gun at another person"
- "woman running through rain"
- "car exploding in street"
- "two people having intense conversation"

Respond with ONLY the description, nothing else."""

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_base64],
        "stream": False,
        "options": {
            "temperature": 0.3,  # Lower temperature for more consistent descriptions
        }
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        description = result.get('response', '').strip()
        # Clean up the description - remove quotes if present
        description = description.strip('"\'')
        return description
    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to Ollama. Make sure Ollama is running (ollama serve)")
        return None
    except Exception as e:
        print(f"Error getting description from Ollama: {e}")
        return None

def check_ollama_available(model="llava"):
    """Check if Ollama is running and the model is available."""
    try:
        # Check if Ollama is running
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        response.raise_for_status()
        
        # Check if the model is available
        models = response.json().get('models', [])
        model_names = [m.get('name', '').split(':')[0] for m in models]
        
        if model.split(':')[0] not in model_names:
            print(f"Model '{model}' not found. Available models: {model_names}")
            print(f"Pull the model with: ollama pull {model}")
            return False
        
        return True
    except requests.exceptions.ConnectionError:
        print("Ollama is not running. Start it with: ollama serve")
        return False
    except Exception as e:
        print(f"Error checking Ollama: {e}")
        return False

def process_gifs_folder(folder_path, model="llava", skip_existing=False):
    """Process all GIFs in a folder and add descriptions to metadata."""
    
    # Check if Ollama is available
    if not check_ollama_available(model):
        return
    
    json_path = os.path.join(folder_path, 'gifs_metadata.json')
    
    # Load existing metadata
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    else:
        print(f"No gifs_metadata.json found in {folder_path}")
        # Try to build metadata from GIF files
        metadata = {}
        for filename in os.listdir(folder_path):
            if filename.endswith('.gif'):
                metadata[filename] = {
                    'quote': '',
                    'startTime': '',
                    'endTime': ''
                }
    
    total = len(metadata)
    processed = 0
    skipped = 0
    
    print(f"\nProcessing {total} GIFs in {folder_path}...")
    print(f"Using model: {model}")
    print("-" * 60)
    
    for filename, data in metadata.items():
        # Skip if already has description and skip_existing is True
        if skip_existing and data.get('description'):
            skipped += 1
            continue
        
        gif_path = os.path.join(folder_path, filename)
        
        # Check if GIF file exists (might be in a batch subfolder)
        if not os.path.exists(gif_path):
            # Check batch folders
            for subfolder in os.listdir(folder_path):
                subfolder_path = os.path.join(folder_path, subfolder)
                if os.path.isdir(subfolder_path) and subfolder.startswith('batch_'):
                    potential_path = os.path.join(subfolder_path, filename)
                    if os.path.exists(potential_path):
                        gif_path = potential_path
                        break
        
        if not os.path.exists(gif_path):
            print(f"⚠ GIF not found: {filename}")
            continue
        
        processed += 1
        print(f"[{processed}/{total}] Processing: {filename[:50]}...")
        
        # Extract frame from GIF
        image_base64 = extract_frame_from_gif(gif_path)
        if not image_base64:
            continue
        
        # Get description from Ollama
        description = get_description_from_ollama(image_base64, model)
        if description:
            data['description'] = description
            print(f"    → {description}")
            
            # Save after each update (in case of interruption)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        else:
            print(f"    → Failed to get description")
    
    print("-" * 60)
    print(f"Done! Processed: {processed}, Skipped: {skipped}")
    print(f"Metadata saved to: {json_path}")

def main():
    parser = argparse.ArgumentParser(
        description='Add AI-generated descriptions to GIF metadata using local Ollama vision model.'
    )
    parser.add_argument('--folder', required=True, 
                        help='Path to folder containing GIFs and gifs_metadata.json')
    parser.add_argument('--model', default='llava',
                        help='Ollama vision model to use (default: llava). Options: llava, llava:13b, llava:34b, bakllava')
    parser.add_argument('--skip-existing', action='store_true',
                        help='Skip GIFs that already have descriptions')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.folder):
        print(f"Error: Folder not found: {args.folder}")
        return
    
    process_gifs_folder(args.folder, args.model, args.skip_existing)

if __name__ == '__main__':
    main()
