#!/usr/bin/env python3
"""
Add AI-generated descriptions to GIF metadata using a local Ollama vision model.

Prerequisites:
1. Install Ollama: https://ollama.com/download
2. Pull a vision model: ollama pull llava
3. Make sure Ollama is running: ollama serve

Usage:
    python add_gif_descriptions.py F1.cfg
    python add_gif_descriptions.py F1.cfg --model "llava:13b"
    python add_gif_descriptions.py F1.cfg --skip-existing
    python add_gif_descriptions.py --folder "/path/to/gifs"
"""

import os
import json
import argparse
import configparser
from describe import (
    check_ollama_available,
    describe_gif,
    find_gif_path,
    OllamaFatalError,
)


def resolve_folder_from_cfg(config_path):
    """Read a .cfg file and derive the GIF output folder path."""
    cfg = configparser.ConfigParser()
    cfg.read(config_path)
    if 'movie' not in cfg:
        print(f"Error: No [movie] section found in {config_path}")
        return None
    section = cfg['movie']
    movie_path = section.get('movie_path', '').strip()
    output_folder = section.get('output_folder', 'gifs_output').strip() or 'gifs_output'
    if not movie_path:
        print(f"Error: No movie_path set in {config_path}")
        return None
    if os.path.isabs(output_folder):
        return output_folder
    movie_dir = os.path.dirname(os.path.abspath(movie_path))
    return os.path.join(movie_dir, output_folder)


def process_gifs_folder(folder_path, model="llava", skip_existing=False):
    """Process all GIFs in a folder and add descriptions to metadata."""
    if not check_ollama_available(model):
        return

    json_path = os.path.join(folder_path, 'gifs_metadata.json')

    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    else:
        print(f"No gifs_metadata.json found in {folder_path}")
        metadata = {}
        for filename in os.listdir(folder_path):
            if filename.endswith('.gif'):
                metadata[filename] = {'quote': '', 'startTime': '', 'endTime': ''}

    total = len(metadata)
    processed = 0
    skipped = 0

    print(f"\nProcessing {total} GIFs in {folder_path}...")
    print(f"Using model: {model}")
    print("-" * 60)

    for filename, data in metadata.items():
        if skip_existing and data.get('description'):
            skipped += 1
            continue

        gif_path = find_gif_path(filename, folder_path)
        if not gif_path:
            print(f"  GIF not found: {filename}")
            continue

        processed += 1
        print(f"[{processed}/{total}] Processing: {filename[:50]}...")

        try:
            description = describe_gif(gif_path, model)
        except OllamaFatalError as e:
            print(f"\n*** FATAL: {e}")
            print("*** Stopping.")
            break

        if description:
            data['description'] = description
            print(f"    -> {description}")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        else:
            print(f"    -> Failed to get description")

    print("-" * 60)
    print(f"Done! Processed: {processed}, Skipped: {skipped}")
    print(f"Metadata saved to: {json_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Add AI-generated descriptions to GIF metadata using local Ollama vision model.',
        usage='%(prog)s [CONFIG.cfg | --folder PATH] [options]'
    )
    parser.add_argument('config', nargs='?', default=None,
                        help='Path to a .cfg configuration file (e.g. F1.cfg)')
    parser.add_argument('--folder', default=None,
                        help='Path to folder containing GIFs and gifs_metadata.json')
    parser.add_argument('--model', default='llava',
                        help='Ollama vision model to use (default: llava)')
    parser.add_argument('--skip-existing', action='store_true',
                        help='Skip GIFs that already have descriptions')

    args = parser.parse_args()

    folder = args.folder
    if args.config:
        if not os.path.isfile(args.config):
            print(f"Error: Config file not found: {args.config}")
            return
        folder = resolve_folder_from_cfg(args.config)
        if not folder:
            return
        print(f"Loaded configuration from: {args.config}")
        print(f"GIF folder: {folder}")

    if not folder:
        parser.error('Provide a .cfg file or --folder path')

    if not os.path.exists(folder):
        print(f"Error: Folder not found: {folder}")
        return

    process_gifs_folder(folder, args.model, args.skip_existing)


if __name__ == '__main__':
    main()
