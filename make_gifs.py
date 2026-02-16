#!/usr/bin/env python3

import ast
import argparse
import imageio
import random
import re
import os
import pysrt
import subprocess
import configparser    
import time
import tempfile
import ffmpeg
import os
import time
import subprocess
import pysrt
import math
from PIL import Image, ImageDraw, ImageFont
from numpy import array
from numpy import array
from PIL import Image, ImageFont, ImageDraw
from PIL import ImageEnhance  # Add this import
import shutil  # Add this import for checking ImageMagick availability
import json
from datetime import datetime

# Timestamp helper for performance profiling
def ts_print(message):
    """Print a message with a timestamp prefix for performance analysis."""
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[{timestamp}] {message}")

# defaults

PALLETSIZE = 256  # number of colors used in the gif, rounded to a power of two
WIDTH = None  # will be set dynamically
HEIGHT = None  # will be set dynamically
ORIGINAL_WIDTH = None  # original frame width before any reductions
ORIGINAL_HEIGHT = None  # original frame height before any reductions
FRAME_DURATION = 0.1  # how long a frame/image is displayed
PADDING = [0]  # seconds to widen the capture-window
DITHER = 2  # only every <dither> image will be used to generate the gif
FRAMES = 0  # how many frames to export, 0 means as many as are available
SCREENCAP_PATH = os.path.join(os.path.dirname(__file__), "screencaps")
FONT_PATH = "fonts/DejaVuSansCondensed-BoldOblique.ttf"
FONT_SIZE = 19  # Increased by 20% from 16

# Add ffmpeg_path as a global variable
ffmpeg_path = "ffmpeg"  # Assuming ffmpeg is in the system PATH

def movie_sanity_check(movie):
    # see if video_path is set
    if 'movie_path' not in movie or not os.path.exists(movie['movie_path']):
        print('Movie \'{}\' has no readable video_path set'.format(
            movie['title'] if 'title' in movie else 'unknown'))
        return False

    if 'subtitle_path' not in movie or not os.path.exists(
            movie['subtitle_path']):
        candidate = movie['movie_path'][:-3] + "srt"
        if os.path.exists(candidate):
            movie['subtitle_path'] = candidate
            return movie

        candidate = movie['movie_path'][:-3] + "eng.srt"
        if os.path.exists(candidate):
            movie['subtitle_path'] = candidate
            return movie
        return False

    return movie


def get_movie_by_slug(slug, movies):
    for movie in movies:
        if (movie['slug'] == slug):
            return movie
    print('movie with slug "{}" not found in config.'.format(slug))
    exit(1)


def striptags(data):
    #  I'm a bad person, don't ever do this.
    #  Only okay, because of how basic the tags are.
    p = re.compile(r'<.*?>')
    data = p.sub('', data)
    
    # Remove emojis and special unicode characters (music notes, etc.)
    # Keep only basic ASCII printable characters plus common punctuation
    # This removes ♪, ♫, emojis, and other special symbols
    # Allow: letters, numbers, spaces, and common punctuation: . , ! ? ' " - : ; ( ) [ ] / \ @ # $ % & * + = _ ~ ` ^
    data = re.sub(r'[^\x20-\x7E\n\r]', '', data)
    
    # Clean up multiple spaces that may result from removing characters
    data = re.sub(r'  +', ' ', data)
    
    return data.strip()

def sanitize_text(text):
    """Sanitize text to remove malformed characters and encoding issues."""
    if not text:
        return ""
    try:
        # Try to fix encoding issues by encoding to latin-1 then decoding to utf-8
        # This handles cases where text was incorrectly decoded
        text = text.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')
    except:
        pass
    # Remove non-printable characters except newlines and tabs
    # Keep only printable ASCII and common Unicode characters
    sanitized = ''.join(char for char in text if char.isprintable() or char in '\n\t')
    # Remove common malformed character sequences
    sanitized = re.sub(r'â[ª©®]', '', sanitized)  # Remove common malformed sequences
    sanitized = re.sub(r'[^\x20-\x7E\u00A0-\uFFFF]', '', sanitized)  # Keep printable ASCII and Unicode
    return sanitized.strip()

def remove_trailing_period(text):
    """Remove trailing period from text if it exists."""
    if not text:
        return text
    return text.rstrip('.')


def remove_leading_bracket_word(text):
    """Remove leading bracketed word(s) from text (e.g., '[Sommerville] Hello' -> 'Hello').
    
    This handles patterns like:
    - [Sommerville] That's cheek to jowl
    - [whispers] Watch, watch, watch
    - [in English] What's your name
    
    Returns the text with leading bracket patterns removed and trimmed.
    """
    if not text:
        return text
    # Match one or more leading bracket patterns at the start of the text
    # Pattern: [anything] possibly followed by more [anything] patterns
    cleaned = re.sub(r'^(\s*\[[^\]]*\]\s*)+', '', text)
    return cleaned.strip()


def get_subtitle_tracks(movie_path):
    """Get all subtitle tracks from a video file using ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', '-select_streams', 's', movie_path],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            import json as json_module
            data = json_module.loads(result.stdout)
            tracks = []
            for stream in data.get('streams', []):
                track_info = {
                    'index': stream.get('index'),
                    'codec_name': stream.get('codec_name', 'unknown'),
                    'language': stream.get('tags', {}).get('language', 'unknown'),
                    'title': stream.get('tags', {}).get('title', ''),
                }
                tracks.append(track_info)
            return tracks
    except Exception as e:
        print(f"Warning: Could not detect subtitle tracks: {e}")
    return []


def get_subtitle_preferences_path(movie_path):
    """Get the path to the subtitle preferences JSON file for a movie."""
    movie_dir = os.path.dirname(os.path.abspath(movie_path))
    movie_name = os.path.splitext(os.path.basename(movie_path))[0]
    return os.path.join(movie_dir, f".{movie_name}_subtitle_prefs.json")


def load_subtitle_preference(movie_path):
    """Load saved subtitle track preference for a movie."""
    prefs_path = get_subtitle_preferences_path(movie_path)
    if os.path.exists(prefs_path):
        try:
            with open(prefs_path, 'r') as f:
                return json.load(f)
        except:
            pass
    return None


def save_subtitle_preference(movie_path, track_index, track_info):
    """Save subtitle track preference for a movie."""
    prefs_path = get_subtitle_preferences_path(movie_path)
    prefs = {
        'track_index': track_index,
        'track_info': track_info
    }
    try:
        with open(prefs_path, 'w') as f:
            json.dump(prefs, f, indent=2)
        print(f"Subtitle preference saved to: {prefs_path}")
    except Exception as e:
        print(f"Warning: Could not save subtitle preference: {e}")


def extract_subtitle_track(movie_path, track_index, output_path=None):
    """Extract a subtitle track from a video file to an SRT file."""
    if output_path is None:
        movie_dir = os.path.dirname(os.path.abspath(movie_path))
        movie_name = os.path.splitext(os.path.basename(movie_path))[0]
        output_path = os.path.join(movie_dir, f".{movie_name}_extracted_track{track_index}.srt")
    
    # Check if we already extracted this track
    if os.path.exists(output_path):
        print(f"Using cached extracted subtitles: {output_path}")
        return output_path
    
    print(f"Extracting subtitle track {track_index}... ", end="", flush=True)
    
    try:
        # Use ffmpeg to extract the subtitle track
        # -c:s copy = copy subtitle stream without re-encoding (much faster)
        # -an = no audio processing
        # -vn = no video processing  
        result = subprocess.run(
            [ffmpeg_path, '-y', '-i', movie_path, '-map', f'0:{track_index}', '-c:s', 'srt', '-an', '-vn', output_path],
            capture_output=True, text=True, timeout=60  # 60 second timeout
        )
        if result.returncode == 0 and os.path.exists(output_path):
            print("done!")
            return output_path
        else:
            print("failed!")
            print(f"Warning: Failed to extract subtitle track: {result.stderr}")
    except subprocess.TimeoutExpired:
        print("timeout!")
        print("Warning: Subtitle extraction timed out after 60 seconds")
    except Exception as e:
        print("error!")
        print(f"Warning: Could not extract subtitle track: {e}")
    return None


def prompt_subtitle_track_selection(tracks, movie_path):
    """Prompt user to select a subtitle track from multiple options."""
    print("\n" + "="*60)
    print("Multiple subtitle tracks found in video file:")
    print("="*60)
    
    for i, track in enumerate(tracks):
        lang = track.get('language', 'unknown')
        title = track.get('title', '')
        codec = track.get('codec_name', 'unknown')
        index = track.get('index')
        
        display_title = f" - {title}" if title else ""
        print(f"  [{i+1}] Track {index}: {lang}{display_title} ({codec})")
    
    print(f"  [0] Skip - don't use embedded subtitles")
    print("="*60)
    
    while True:
        try:
            choice = input(f"Select subtitle track (0-{len(tracks)}): ").strip()
            choice_num = int(choice)
            if 0 <= choice_num <= len(tracks):
                break
            print(f"Please enter a number between 0 and {len(tracks)}")
        except ValueError:
            print("Please enter a valid number")
    
    if choice_num == 0:
        return None, None
    
    selected_track = tracks[choice_num - 1]
    
    # Ask if user wants to save this preference
    save_choice = input("Save this choice for future runs? (y/n): ").strip().lower()
    if save_choice in ('y', 'yes'):
        save_subtitle_preference(movie_path, selected_track['index'], selected_track)
    
    return selected_track['index'], selected_track


def draw_text(draw, image_width, image_height, text, font, text_color="white", stroke_width=2, uppercase=False, italicize=False, text_padding=5, bottom_padding=None, subtitle_size=None):
    """Draws text within the image bounds with optional border/stroke and italicization."""
    # Convert to uppercase if requested
    if uppercase:
        text = text.upper()
    
    # Use bottom_padding if provided, otherwise use text_padding
    if bottom_padding is None:
        bottom_padding = text_padding
    
    # Account for stroke width in total text dimensions
    stroke_offset = stroke_width if stroke_width > 0 else 0
    
    # Calculate safe area (image bounds minus padding)
    safe_left = text_padding + stroke_offset
    safe_right = image_width - text_padding - stroke_offset
    safe_top = text_padding + stroke_offset
    safe_bottom = image_height - bottom_padding - stroke_offset
    
    # Ensure text fits within safe area
    available_width = safe_right - safe_left
    available_height = safe_bottom - safe_top
    
    # Get initial text dimensions
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    # Auto-scale text if it doesn't fit within the frame
    current_font = font
    max_iterations = 20  # Prevent infinite loops
    iteration = 0
    
    while (text_width > available_width or text_height > available_height) and iteration < max_iterations:
        iteration += 1
        
        # Calculate scale factors for width and height
        width_scale = available_width / text_width if text_width > 0 else 1.0
        height_scale = available_height / text_height if text_height > 0 else 1.0
        # Use the smaller scale to ensure both dimensions fit
        scale = min(width_scale, height_scale) * 0.95  # 0.95 for a small safety margin
        
        # Get current font size (try to extract from font)
        current_size = subtitle_size
        if current_size is None:
            # Try to get size from font object
            try:
                if hasattr(current_font, 'size'):
                    current_size = current_font.size
                elif hasattr(current_font, 'getsize'):
                    # For older PIL versions
                    current_size = current_font.getsize('M')[1]
                else:
                    # Default fallback
                    current_size = 20
            except:
                current_size = 20
        
        # Calculate new font size
        new_size = max(int(current_size * scale), 8)  # Minimum size of 8px
        
        if new_size >= current_size:
            break  # Can't scale down further
        
        # Create new font with scaled size
        try:
            # Try to reload font from the default font path
            font_path = os.path.join(os.path.dirname(__file__), FONT_PATH)
            if os.path.exists(font_path):
                current_font = ImageFont.truetype(font_path, new_size)
            else:
                # Try system fonts
                system_fonts = [
                    "arialbd.ttf",  # Windows
                    "Arial Bold.ttf",  # macOS
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Linux alternative
                ]
                font_loaded = False
                for sys_font in system_fonts:
                    try:
                        current_font = ImageFont.truetype(sys_font, new_size)
                        font_loaded = True
                        break
                    except:
                        continue
                if not font_loaded:
                    # Use default font (can't scale, so break)
                    break
        except:
            # If font creation fails, use original font
            break
        
        # Recalculate text dimensions with new font
        text_bbox = draw.textbbox((0, 0), text, font=current_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    
    # Use the scaled font (or original if no scaling was needed)
    font = current_font
    
    # Center horizontally within safe area
    x = max(safe_left, min(safe_left + (available_width - text_width) // 2, safe_right - text_width))
    # Position text at the bottom of the safe area (using bottom_padding)
    y = max(safe_top, min(safe_bottom - text_height, image_height - text_height - bottom_padding - stroke_offset))
    
    if italicize:
        # Draw text to a temporary image, apply skew transform, then composite back
        # Create a temporary image large enough for the text
        temp_width = int(text_width * 1.5)  # Extra width for skew
        temp_height = int(text_height * 1.5)  # Extra height for safety
        temp_image = Image.new('RGBA', (temp_width, temp_height), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_image)
        
        # Draw text on temporary image
        temp_x = temp_width // 4
        temp_y = temp_height // 4
        if stroke_width > 0:
            temp_draw.text((temp_x, temp_y), text, font=font, fill=text_color, stroke_width=stroke_width, stroke_fill="black")
        else:
            temp_draw.text((temp_x, temp_y), text, font=font, fill=text_color)
        
        # Apply skew transform to italicize (shear horizontally)
        # Skew matrix: [1, skew_x, 0, 0, 1, 0]
        skew_angle = -15  # Negative for right-leaning italic
        transform_matrix = (1, math.tan(math.radians(skew_angle)), 0, 0, 1, 0)
        italic_image = temp_image.transform(temp_image.size, Image.Transform.AFFINE, transform_matrix, Image.Resampling.BILINEAR, fillcolor=(0, 0, 0, 0))
        
        # Get the bounding box of the non-transparent area
        bbox = italic_image.getbbox()
        if bbox:
            italic_image = italic_image.crop(bbox)
            # Calculate position to center the italicized text within safe area
            italic_width = italic_image.size[0]
            italic_height = italic_image.size[1]
            # Center horizontally within safe area
            paste_x = max(safe_left, min(safe_left + (available_width - italic_width) // 2, safe_right - italic_width))
            # Position at bottom of safe area (using bottom_padding)
            paste_y = max(safe_top, min(safe_bottom - italic_height, image_height - italic_height - bottom_padding - stroke_offset))
            
            # Get the image from the draw object and paste the italicized text
            image = draw.im if hasattr(draw, 'im') else None
            if image:
                image.paste(italic_image, (paste_x, paste_y), italic_image)
    else:
        # Draw text with black border/stroke around white text (normal, non-italic)
        if stroke_width > 0:
            # Draw text with stroke (border) - stroke_fill is the border color, fill is the text color
            draw.text((x, y), text, font=font, fill=text_color, stroke_width=stroke_width, stroke_fill="black")
        else:
            # No stroke, just draw the text
            draw.text((x, y), text, font=font, fill=text_color)


def getDetails():
    # Get location of video file and subtitles
    seriesLocation = "/mnt/f/sopranos/The Sopranos - The Complete Series (Season 1, 2, 3, 4, 5 & 6) + Extras/"
    randomSeason = random.choice(os.listdir(seriesLocation))
    
    #print("getEpisode randomSeason = ", randomSeason)
    randomSeasonLocation = seriesLocation + randomSeason
    #print("getEpisode randomSeasonLocation = ", randomSeasonLocation)
    randomEpisode = random.choice(os.listdir(randomSeasonLocation))
    #print("getEpisode randomEpisode = ", randomEpisode)
    randomEpisodeLocation = randomSeasonLocation + "/" + randomEpisode
    #print("getEpisode randomEpisodeLocation = ", randomEpisodeLocation)
    subsLocation = "/mnt/f/sopranos/The Sopranos Subtitles/" + randomSeason + "/" + os.path.splitext(randomEpisode)[0] + ".srt"
    #print("getEpisode subsLocation = ", subsLocation)

    d = dict()
    d['subsLocation'] = subsLocation
    d['vidLocation'] = randomEpisodeLocation
    d['vidName'] = os.path.splitext(randomEpisode)[0]
    return d
    # Create gif
    #gifFilename = "sopranos_gif_" + str(uuid.uuid4()) + ".gif"
    #respText = make_gif_new(randomEpisodeLocation, subsLocation)

def get_video_resolution(movie_path):
    """Get the width and height of the input video using ffprobe."""
    import json
    cmd = [
        ffmpeg_path.replace("ffmpeg", "ffprobe"),
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'json',
        movie_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    try:
        info = json.loads(result.stdout)
        width = info['streams'][0]['width']
        height = info['streams'][0]['height']
        return width, height
    except Exception as e:
        print(f"Could not get video resolution: {e}")
        # fallback to default aspect ratio if detection fails
        return 1280, 536

def load_existing_metadata(output_dir, config_title=None):
    """Load existing GIF metadata from JSON file if it exists."""
    if config_title:
        json_filename = os.path.join(output_dir, f'gifs_metadata_{config_title}.json')
    else:
        json_filename = os.path.join(output_dir, 'gifs_metadata.json')
    if os.path.exists(json_filename):
        try:
            with open(json_filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def check_gif_exists(start_time, end_time, quote, existing_metadata):
    """Check if a GIF with the same start/end time and quote already exists."""
    start_time_str = time.strftime('%H:%M:%S', time.gmtime(start_time))
    end_time_str = time.strftime('%H:%M:%S', time.gmtime(end_time))
    sanitized_quote = sanitize_text(quote) if quote else ''
    
    for filename_key, metadata in existing_metadata.items():
        if (metadata.get('startTime') == start_time_str and 
            metadata.get('endTime') == end_time_str and
            sanitize_text(metadata.get('quote', '')) == sanitized_quote):
            return True
    return False

def get_batch_folder_path(output_dir, gif_index, batch_size):
    """Get the batch folder path for a given GIF index."""
    if batch_size is None or batch_size <= 0:
        return output_dir
    batch_number = (gif_index // batch_size) + 1
    batch_folder = os.path.join(output_dir, f"batch_{batch_number:03d}")
    if not os.path.exists(batch_folder):
        os.makedirs(batch_folder)
    return batch_folder

def generate_gifs(movie_path, subtitle_path=None, output_dir='/mnt/x/28dayslatergifs/', interval=5, start_time_str="00:00:00", max_filesize=None, debug=False, random_times=False, no_hdr=False, boost_colors=0, boost_frame_colors=0, quotes=True, subtitle_color="white", subtitle_size=None, random_quote=False, save_json=False, check_history=False, text_border=2, uppercase=False, italicize=False, max_gifs=None, text_padding=5, bottom_padding=None, trailing_period=True, output_batch_folder_size=None, remove_leading_quote_bracket_word=False, config_title=None, target_width=None):
    global WIDTH, HEIGHT, ORIGINAL_WIDTH, ORIGINAL_HEIGHT, SCREENCAP_PATH
    
    # Set up config-specific screencaps folder to avoid conflicts between configs
    if config_title:
        SCREENCAP_PATH = os.path.join(os.path.dirname(__file__), f"screencaps_{config_title}")
    else:
        SCREENCAP_PATH = os.path.join(os.path.dirname(__file__), "screencaps")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if not os.path.exists(SCREENCAP_PATH):
        os.makedirs(SCREENCAP_PATH)
    WIDTH, HEIGHT = get_video_resolution(movie_path)
    
    # Apply target_width scaling if specified (for performance optimization)
    if target_width and WIDTH > target_width:
        scale_factor = target_width / WIDTH
        new_height = int(HEIGHT * scale_factor)
        # Ensure dimensions are even (required by some encoders)
        target_width = target_width - (target_width % 2)
        new_height = new_height - (new_height % 2)
        ts_print(f"Applying target_width: scaling from {WIDTH}x{HEIGHT} to {target_width}x{new_height}")
        WIDTH = target_width
        HEIGHT = new_height
    
    ORIGINAL_WIDTH = WIDTH  # Store original width before any reductions
    ORIGINAL_HEIGHT = HEIGHT  # Store original height for subtitle size calculation

    # If subtitle_size not specified, use default of 20px
    if subtitle_size is None:
        subtitle_size = 20
    
    # Track GIF count for batch folder organization
    gif_count = 0

    # Clear the screencaps folder
    for file in os.listdir(SCREENCAP_PATH):
        file_path = os.path.join(SCREENCAP_PATH, file)
        if os.path.isfile(file_path):
            os.remove(file_path)

    # Use non-oblique font when italicize is False, otherwise use the oblique font
    if not italicize:
        # Try to use a system font (non-oblique) first
        try:
            # Try common system fonts that are bold but not oblique
            system_fonts = [
                "arialbd.ttf",  # Windows
                "Arial Bold.ttf",  # macOS
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Linux alternative
            ]
            font_loaded = False
            for sys_font in system_fonts:
                try:
                    font = ImageFont.truetype(sys_font, subtitle_size)
                    font_loaded = True
                    break
                except:
                    continue
            if not font_loaded:
                # Try PIL's default font as fallback (usually non-oblique)
                try:
                    font = ImageFont.load_default()
                    # Scale default font if possible (default font is usually small)
                    # Note: default font size is fixed, so we'll use it as-is
                except:
                    # Final fallback to default oblique font if nothing else works
                    font_path = os.path.join(os.path.dirname(__file__), FONT_PATH)
                    font = ImageFont.truetype(font_path, subtitle_size)
        except:
            # Fall back to default oblique font if anything fails
            font_path = os.path.join(os.path.dirname(__file__), FONT_PATH)
            font = ImageFont.truetype(font_path, subtitle_size)
    else:
        # Use the oblique font when italicize is True (will apply additional skew)
        font_path = os.path.join(os.path.dirname(__file__), FONT_PATH)
        font = ImageFont.truetype(font_path, subtitle_size)

    subs = None
    # If no subtitle path provided, try to find first .srt file in movie's directory
    if not subtitle_path:
        movie_dir = os.path.dirname(os.path.abspath(movie_path))
        if os.path.exists(movie_dir):
            srt_files = [f for f in os.listdir(movie_dir) if f.lower().endswith('.srt')]
            if srt_files:
                subtitle_path = os.path.join(movie_dir, sorted(srt_files)[0])
                print(f"Auto-detected subtitle file: {subtitle_path}\n")
    
    # If still no subtitle path, check for embedded subtitle tracks in the video
    if not subtitle_path:
        # First check if we have a saved preference
        saved_pref = load_subtitle_preference(movie_path)
        if saved_pref:
            track_index = saved_pref.get('track_index')
            track_info = saved_pref.get('track_info', {})
            print(f"Using saved subtitle preference: Track {track_index} ({track_info.get('language', 'unknown')})")
            extracted_path = extract_subtitle_track(movie_path, track_index)
            if extracted_path:
                subtitle_path = extracted_path
                print(f"Extracted subtitle track to: {subtitle_path}\n")
        else:
            # No saved preference, check for embedded tracks
            tracks = get_subtitle_tracks(movie_path)
            if len(tracks) > 1:
                # Multiple tracks found, prompt user to select
                track_index, track_info = prompt_subtitle_track_selection(tracks, movie_path)
                if track_index is not None:
                    extracted_path = extract_subtitle_track(movie_path, track_index)
                    if extracted_path:
                        subtitle_path = extracted_path
                        print(f"Extracted subtitle track to: {subtitle_path}\n")
            elif len(tracks) == 1:
                # Only one track, use it automatically
                track = tracks[0]
                print(f"Found single embedded subtitle track: {track.get('language', 'unknown')} ({track.get('codec_name', 'unknown')})")
                extracted_path = extract_subtitle_track(movie_path, track['index'])
                if extracted_path:
                    subtitle_path = extracted_path
                    print(f"Extracted subtitle track to: {subtitle_path}\n")
    
    if subtitle_path and os.path.exists(subtitle_path):
        subs = pysrt.open(subtitle_path, encoding='iso-8859-1')  # Specify the correct encoding

    duration = get_video_duration(movie_path)
    
    # Load existing metadata if check_history is enabled
    existing_metadata = {}
    if check_history:
        existing_metadata = load_existing_metadata(output_dir, config_title)
        if existing_metadata:
            print(f"Loaded {len(existing_metadata)} existing GIF entries from history.")
    
    # Dictionary to store GIF metadata if save_json is enabled
    gif_metadata = {}
    # If check_history is enabled, start with existing metadata
    if check_history and existing_metadata:
        gif_metadata = existing_metadata.copy()
    
    # Counter for tracking number of GIFs created
    gifs_created = 0
    
    # Handle randomQuote flag
    if random_quote:
        if quotes:
            # Export ALL quotes, but in random order with random selection
            if subs:
                all_subs = list(subs)
                if len(all_subs) > 0:
                    # Filter to only non-empty quotes
                    valid_subs = [sub for sub in all_subs if striptags(sub.text).strip()]
                    if len(valid_subs) > 0:
                        # Pre-calculate all GIFs (quotes and gaps)
                        gif_tasks = []
                        
                        # Add all quote GIFs
                        for sub in valid_subs:
                            quote = striptags(sub.text)
                            # Remove leading bracketed words if remove_leading_quote_bracket_word is True
                            if remove_leading_quote_bracket_word and quote:
                                quote = remove_leading_bracket_word(quote)
                            # Remove trailing period if trailing_period is False
                            if not trailing_period and quote:
                                quote = remove_trailing_period(quote)
                            start_time = sub.start.ordinal / 1000.0
                            end_time = sub.end.ordinal / 1000.0
                            gif_tasks.append({
                                'type': 'quote',
                                'quote': quote,
                                'start_time': start_time,
                                'end_time': end_time,
                                'has_quote': True
                            })
                        
                        # If randomTimes is also specified, pre-calculate gap GIFs
                        if random_times:
                            # Sort quotes by start time to find gaps
                            sorted_subs = sorted(valid_subs, key=lambda s: s.start.ordinal)
                            
                            # Fill gap from start of video to first quote
                            if len(sorted_subs) > 0:
                                first_quote_start = sorted_subs[0].start.ordinal / 1000.0
                                if first_quote_start >= interval:
                                    current_gap_time = 0
                                    while current_gap_time + interval <= first_quote_start:
                                        gap_gif_end = min(current_gap_time + interval, first_quote_start)
                                        gif_tasks.append({
                                            'type': 'gap',
                                            'quote': '',
                                            'start_time': current_gap_time,
                                            'end_time': gap_gif_end,
                                            'has_quote': False
                                        })
                                        current_gap_time += interval
                            
                            # Fill gaps between consecutive quotes
                            for i in range(len(sorted_subs) - 1):
                                current_quote_end = sorted_subs[i].end.ordinal / 1000.0
                                next_quote_start = sorted_subs[i + 1].start.ordinal / 1000.0
                                gap_size = next_quote_start - current_quote_end
                                
                                if gap_size >= interval:
                                    current_gap_time = current_quote_end
                                    while current_gap_time + interval <= next_quote_start:
                                        gap_gif_end = min(current_gap_time + interval, next_quote_start)
                                        gif_tasks.append({
                                            'type': 'gap',
                                            'quote': '',
                                            'start_time': current_gap_time,
                                            'end_time': gap_gif_end,
                                            'has_quote': False
                                        })
                                        current_gap_time += interval
                            
                            # Fill gap from last quote to end of video
                            if len(sorted_subs) > 0:
                                last_quote_end = sorted_subs[-1].end.ordinal / 1000.0
                                if duration - last_quote_end >= interval:
                                    current_gap_time = last_quote_end
                                    while current_gap_time + interval <= duration:
                                        gap_gif_end = min(current_gap_time + interval, duration)
                                        gif_tasks.append({
                                            'type': 'gap',
                                            'quote': '',
                                            'start_time': current_gap_time,
                                            'end_time': gap_gif_end,
                                            'has_quote': False
                                        })
                                        current_gap_time += interval
                        
                        # Shuffle all GIFs together for random order
                        random.shuffle(gif_tasks)
                        
                        # Filter out already exported GIFs if check_history is enabled
                        original_count = len(gif_tasks)
                        if check_history:
                            filtered_tasks = []
                            for task in gif_tasks:
                                if not check_gif_exists(task['start_time'], task['end_time'], task['quote'], existing_metadata):
                                    filtered_tasks.append(task)
                            skipped = original_count - len(filtered_tasks)
                            if skipped > 0:
                                print(f"Skipping {skipped} GIFs that already exist in history.")
                            gif_tasks = filtered_tasks
                        
                        # Export all GIFs with unified progress counter
                        total_gifs = len(gif_tasks)
                        if total_gifs == 0:
                            print("No new GIFs to export. All GIFs already exist in history.")
                        else:
                            for idx, task in enumerate(gif_tasks, 1):
                                # Check max_gifs limit
                                if max_gifs is not None and gifs_created >= max_gifs:
                                    print(f"\nReached maximum GIF limit of {max_gifs}. Stopping GIF generation.")
                                    break
                                
                                # Show progress with max_gifs limit if set
                                if max_gifs is not None:
                                    print(f"\nCreating GIF {gifs_created + 1}/{max_gifs} (from quote {idx}/{total_gifs})")
                                else:
                                    print(f"\nExporting GIF from quotes and spaces: {idx}/{total_gifs}")
                                # Determine batch folder if batch organization is enabled
                                if output_batch_folder_size:
                                    batch_folder = get_batch_folder_path(output_dir, gif_count, output_batch_folder_size)
                                    filename = os.path.join(batch_folder, generate_filename(movie_path, task['start_time'], task['end_time'], task['quote']))
                                else:
                                    filename = os.path.join(output_dir, generate_filename(movie_path, task['start_time'], task['end_time'], task['quote']))
                                create_gif(movie_path, task['start_time'], task['end_time'], task['quote'], filename, font, max_filesize, debug, no_hdr, boost_colors, boost_frame_colors, subtitle_color, task['has_quote'], subtitle_size, save_json, gif_metadata, output_dir, text_border, uppercase, italicize, text_padding, bottom_padding, config_title)
                                # Only count if GIF was actually created
                                if os.path.exists(filename):
                                    gifs_created += 1
                                    gif_count += 1
            else:
                print("Warning: --quotes true specified with --randomQuote but no subtitles file found.")
        else:
            # quotes is false - generate random non-quote intervals
            max_start = max(0, duration - interval)
            if max_start > 0:
                # Check max_gifs limit
                if max_gifs is not None and gifs_created >= max_gifs:
                    print(f"\nReached maximum GIF limit of {max_gifs}. Stopping GIF generation.")
                    return
                
                # Show progress with max_gifs limit if set
                if max_gifs is not None:
                    print(f"\nCreating GIF {gifs_created + 1}/{max_gifs}")
                
                current_time = random.randint(0, max_start)
                end_time = min(current_time + interval, duration)
                quote_text = ""  # Don't include quotes
                # Determine batch folder if batch organization is enabled
                if output_batch_folder_size:
                    batch_folder = get_batch_folder_path(output_dir, gif_count, output_batch_folder_size)
                    filename = os.path.join(batch_folder, generate_filename(movie_path, current_time, end_time, quote_text))
                else:
                    filename = os.path.join(output_dir, generate_filename(movie_path, current_time, end_time, quote_text))
                create_gif(movie_path, current_time, end_time, quote_text, filename, font, max_filesize, debug, no_hdr, boost_colors, boost_frame_colors, subtitle_color, quotes, subtitle_size, save_json, gif_metadata, output_dir, text_border, uppercase, italicize, text_padding, bottom_padding, config_title)
                # Only count if GIF was actually created
                if os.path.exists(filename):
                    gifs_created += 1
                    gif_count += 1
        return
    
    # Original logic for non-randomQuote mode
    if random_times:
        start_times = random.sample(range(0, duration, interval), duration // interval)
    else:
        start_times = range(sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time_str.split(":")))), duration, interval)

    for current_time in start_times:
        # Check max_gifs limit
        if max_gifs is not None and gifs_created >= max_gifs:
            print(f"\nReached maximum GIF limit of {max_gifs}. Stopping GIF generation.")
            break
        
        # Show progress with max_gifs limit if set
        if max_gifs is not None:
            print(f"\nCreating GIF {gifs_created + 1}/{max_gifs}")
        
        end_time = min(current_time + interval, duration)
        quote_text = get_quote(subs, current_time, end_time) if subs else ""
        
        # If quotes is False, don't overlay quotes even if they exist
        if not quotes:
            quote_text = ""
        
        # Remove leading bracketed words if remove_leading_quote_bracket_word is True
        if remove_leading_quote_bracket_word and quote_text:
            quote_text = remove_leading_bracket_word(quote_text)
        
        # Remove trailing period if trailing_period is False
        if not trailing_period and quote_text:
            quote_text = remove_trailing_period(quote_text)
        
        # Check if this GIF already exists in history
        if check_history and check_gif_exists(current_time, end_time, quote_text, existing_metadata):
            continue
        
        # Determine batch folder if batch organization is enabled
        if output_batch_folder_size:
            batch_folder = get_batch_folder_path(output_dir, gif_count, output_batch_folder_size)
            filename = os.path.join(batch_folder, generate_filename(movie_path, current_time, end_time, quote_text))
        else:
            filename = os.path.join(output_dir, generate_filename(movie_path, current_time, end_time, quote_text))
        
        create_gif(movie_path, current_time, end_time, quote_text, filename, font, max_filesize, debug, no_hdr, boost_colors, boost_frame_colors, subtitle_color, quotes, subtitle_size, save_json, gif_metadata, output_dir, text_border, uppercase, italicize, text_padding, bottom_padding, config_title)
        # Only count if GIF was actually created
        if os.path.exists(filename):
            gifs_created += 1
            gif_count += 1

def get_video_duration(movie_path):
    result = subprocess.run(
        [ffmpeg_path, '-i', movie_path, '-hide_banner'],
        stderr=subprocess.PIPE, universal_newlines=True
    )
    match = re.search(r"Duration: (\d+):(\d+):(\d+)\.(\d+)", result.stderr)
    if match:
        hours, minutes, seconds, _ = map(int, match.groups())
        return hours * 3600 + minutes * 60 + seconds
    return 0

def get_quote(subs, start_time, end_time):
    if not subs:
        return ""
    start_ms = start_time * 1000
    end_ms = end_time * 1000
    for sub in subs:
        # Check if subtitle overlaps with the interval (not just if it's completely contained)
        # Subtitle overlaps if: it starts before interval ends AND it ends after interval starts
        if sub.start.ordinal < end_ms and sub.end.ordinal > start_ms:
            return striptags(sub.text)
    return ""

def get_random_quote(subs):
    """Get a random quote from subtitles and return (quote, start_time, end_time)."""
    if not subs or len(subs) == 0:
        return None, None, None
    sub = random.choice(subs)
    quote = striptags(sub.text)
    start_time = sub.start.ordinal / 1000.0  # Convert milliseconds to seconds
    end_time = sub.end.ordinal / 1000.0
    return quote, start_time, end_time

def sanitize_quote_for_filename(quote):
    """Sanitize quote text to keep only letters, numbers, spaces, and basic punctuation."""
    if not quote:
        return ""
    # First, try to fix encoding issues
    try:
        quote = quote.encode('latin-1', errors='ignore').decode('utf-8', errors='ignore')
    except:
        pass
    # Keep only: letters (a-z, A-Z), numbers (0-9), spaces, and basic punctuation
    # Basic punctuation: apostrophe, comma, period, exclamation, question mark, dash, underscore
    sanitized = re.sub(r'[^a-zA-Z0-9\s\',.!?\-_]', '', quote)
    # Remove multiple consecutive spaces
    sanitized = re.sub(r'\s+', ' ', sanitized)
    return sanitized.strip()

def generate_filename(movie_path, start_time, end_time, quote):
    media_name = os.path.splitext(os.path.basename(movie_path))[0]
    start_str = time.strftime('%H-%M-%S', time.gmtime(start_time))
    end_str = time.strftime('%H-%M-%S', time.gmtime(end_time))
    # Sanitize quote to keep only letters, numbers, spaces, and basic punctuation
    quote_str = sanitize_quote_for_filename(quote)[:30]
    return f"{media_name}-Start[{start_str}]-End[{end_str}]-Quote[{quote_str}].gif"


def create_gif(movie_path, start_time, end_time, quote, filename, font, max_filesize, debug, no_hdr=False, boost_colors=0, boost_frame_colors=0, subtitle_color="white", quotes=True, subtitle_size=None, save_json=False, gif_metadata=None, output_dir=None, text_border=2, uppercase=False, italicize=False, text_padding=5, bottom_padding=None, config_title=None):
    global WIDTH, HEIGHT
    
    gif_start_time = datetime.now()
    ts_print(f"Starting GIF creation: {os.path.basename(filename)}")
    
    # Reset WIDTH and HEIGHT to original values at the start of each GIF
    # (they may have been reduced by reduce_resolution() in a previous GIF)
    WIDTH = ORIGINAL_WIDTH
    HEIGHT = ORIGINAL_HEIGHT
    
    # OPTIMIZATION: Pre-calculate estimated target resolution to avoid multiple resize iterations
    # This estimates the resolution needed to fit within max_filesize based on typical GIF compression ratios
    if max_filesize:
        duration = end_time - start_time
        num_frames = int(duration / FRAME_DURATION)
        max_filesize_bytes = int(max_filesize * 1024 * 1024)
        
        # Estimate bytes per pixel per frame (empirically ~0.3-0.5 for typical movie content)
        # Using conservative estimate of 0.4 bytes per pixel per frame
        bytes_per_pixel_per_frame = 0.4
        
        # Calculate current estimated size
        current_pixels = WIDTH * HEIGHT
        estimated_size = current_pixels * num_frames * bytes_per_pixel_per_frame
        
        if estimated_size > max_filesize_bytes:
            # Calculate scale factor needed
            scale_factor = math.sqrt(max_filesize_bytes / estimated_size)
            # Apply a safety margin (use 90% of calculated scale to ensure we meet the limit)
            scale_factor *= 0.9
            
            new_width = max(int(WIDTH * scale_factor), 320)
            new_height = max(int(HEIGHT * scale_factor), 180)
            
            # Ensure dimensions are even (required by some encoders)
            new_width = new_width - (new_width % 2)
            new_height = new_height - (new_height % 2)
            
            ts_print(f"Pre-scaling from {WIDTH}x{HEIGHT} to {new_width}x{new_height} (estimated {estimated_size/1024/1024:.1f}MB -> target {max_filesize}MB)")
            WIDTH = new_width
            HEIGHT = new_height
    
    images = []
    duration = end_time - start_time
    
    # Skip if duration is too short (less than 0.1 seconds)
    if duration < 0.1:
        print(f"Warning: Duration too short ({duration:.3f}s) for {filename}. Skipping GIF creation.")
        return
    
    start_str = time.strftime('%H:%M:%S', time.gmtime(start_time))

    # Ensure screencaps folder exists
    if not os.path.exists(SCREENCAP_PATH):
        os.makedirs(SCREENCAP_PATH)

    # Clear the screencaps folder before extracting new frames to avoid including old frames
    for file in os.listdir(SCREENCAP_PATH):
        file_path = os.path.join(SCREENCAP_PATH, file)
        if os.path.isfile(file_path) and file.endswith('.png'):
            os.remove(file_path)

    # Build ffmpeg filter chain
    filters = [f"scale={WIDTH}:{HEIGHT}"]
    if no_hdr:
        # Remove HDR by converting to SDR (simple tonemap)
        filters.append("zscale=t=linear:npl=100,format=rgb24")
    if boost_colors and boost_colors > 0:
        # Boost saturation and contrast
        filters.append(f"eq=contrast={1+boost_colors/100}:saturation={1+boost_colors/100}")

    filter_chain = ",".join(filters)

    ts_print(f"Extracting frames with ffmpeg (duration={duration:.2f}s, resolution={WIDTH}x{HEIGHT})...")
    ffmpeg_start = datetime.now()
    subprocess.call([
        ffmpeg_path, '-ss', start_str, '-i', movie_path, '-t', str(duration),
        '-vf', filter_chain, '-pix_fmt', 'rgb24', '-r', f"{1 / FRAME_DURATION}", SCREENCAP_PATH + '/thumb%05d.png'
    ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    ts_print(f"Frame extraction completed in {(datetime.now() - ffmpeg_start).total_seconds():.2f}s")

    # Small delay to let filesystem sync (helps with WSL/Windows filesystem race conditions)
    import time as time_module
    time_module.sleep(0.5)

    file_names = sorted(fn for fn in os.listdir(SCREENCAP_PATH) if fn.endswith('.png'))
    
    # Check if ffmpeg extracted any frames
    if len(file_names) == 0:
        raise FileNotFoundError(f"ffmpeg failed to extract any frames for {filename}. Check if the video file is accessible and not corrupted.")
    
    ts_print(f"Loading and processing {len(file_names)} frames...")
    frame_load_start = datetime.now()
    for f in file_names:
        file_path = os.path.join(SCREENCAP_PATH, f)
        # Wait for file to be accessible (helps with WSL filesystem sync issues)
        max_retries = 5
        for retry in range(max_retries):
            if os.path.exists(file_path):
                break
            time_module.sleep(0.2)
        else:
            raise FileNotFoundError(f"Screencap file not accessible after {max_retries} retries: {file_path}")
        
        image = Image.open(file_path).convert("RGB")
        # Boost frame colors if requested (use color, contrast, and brightness)
        if boost_frame_colors and boost_frame_colors > 0:
            print(f"Boosting frame colors by {boost_frame_colors}% for {filename}")
            color_enhancer = ImageEnhance.Color(image)
            contrast_enhancer = ImageEnhance.Contrast(image)
            brightness_enhancer = ImageEnhance.Brightness(image)
            # Apply all three enhancements
            image = color_enhancer.enhance(1 + boost_frame_colors / 100)
            image = contrast_enhancer.enhance(1 + boost_frame_colors / 100)
            image = brightness_enhancer.enhance(1 + (boost_frame_colors / 200))  # brightness less aggressive
        draw = ImageDraw.Draw(image)
        if quote and quotes:
            draw_text(draw, image.size[0], image.size[1], quote, font, subtitle_color, text_border, uppercase, italicize, text_padding, bottom_padding, subtitle_size)
        images.append(image.resize((WIDTH, HEIGHT)))

    # Check if we have any images before trying to save
    if len(images) == 0:
        print(f"Warning: No frames extracted for {filename}. Skipping GIF creation.")
        return
    
    ts_print(f"Frame loading completed in {(datetime.now() - frame_load_start).total_seconds():.2f}s")

    # Save the GIF with looping enabled
    ts_print(f"Saving GIF with {len(images)} frames...")
    save_start = datetime.now()
    # subrectangles=False prevents transparency/compression artifacts by rendering each frame fully
    # Convert FRAME_DURATION from seconds to milliseconds for imageio (e.g., 0.1s -> 100ms)
    frame_duration_ms = int(FRAME_DURATION * 1000)
    imageio.mimsave(filename, [array(img) for img in images], palettesize=PALLETSIZE, duration=frame_duration_ms, loop=0, subrectangles=False)

    ts_print(f"Initial GIF save completed in {(datetime.now() - save_start).total_seconds():.2f}s")
    
    # Log the initial file size
    initial_filesize = os.path.getsize(filename)
    initial_filesize_mb = initial_filesize / (1024 * 1024)
    ts_print(f"Initial GIF size: {initial_filesize_mb:.2f} MB")

    # Ensure the GIF does not exceed the specified maximum file size
    if max_filesize:
        max_filesize_bytes = int(max_filesize * 1024 * 1024)  # Convert MB to bytes
        reduction_iteration = 0
        while os.path.getsize(filename) > max_filesize_bytes:
            reduction_iteration += 1
            ts_print(f"Reduction iteration {reduction_iteration}: GIF size {os.path.getsize(filename)} exceeds limit of {max_filesize_bytes} bytes. Reducing resolution...")
            reduce_start = datetime.now()
            reduce_resolution()
            regenerate_gif(images, filename)
            optimize_gif(filename, max_filesize_bytes, debug)
            ts_print(f"Reduction iteration {reduction_iteration} completed in {(datetime.now() - reduce_start).total_seconds():.2f}s")
    else:
        # Only create a resized version under 15MB if maxFilesize is not specified
        create_resized_gif(filename)

    # Log details about the generated GIF
    total_gif_time = (datetime.now() - gif_start_time).total_seconds()
    ts_print(f"✓ GIF completed in {total_gif_time:.2f}s total")
    print(f"Generated GIF: {filename}")
    end_str = time.strftime('%H:%M:%S', time.gmtime(end_time))
    print(f"Start/End Time: {start_str} / {end_str}")
    print(f"Number of Frames: {len(images)} | Frame Duration: {FRAME_DURATION} seconds | FPS: {1 / FRAME_DURATION}")
    # Ensure subtitle_size is set (should already be calculated, but safety check)
    if subtitle_size is None:
        subtitle_size = 20
    print(f"Subtitle: Color={subtitle_color} | Size={subtitle_size}px")
    print(f"Quote: {'Yes' if quote else 'No'}")
    # Print the sanitized quote before the output filename
    if quote:
        sanitized_quote = sanitize_text(quote)
        print(f"Quote Text: {sanitized_quote}")
    print(f"Output Filename: {filename}")
    print("-" * 80)  # Separator divider line
    
    # Add to metadata if save_json is enabled
    if save_json and gif_metadata is not None:
        start_time_str = time.strftime('%H:%M:%S', time.gmtime(start_time))
        end_time_str = time.strftime('%H:%M:%S', time.gmtime(end_time))
        # Use just the filename, not the full path
        filename_key = os.path.basename(filename)
        gif_metadata[filename_key] = {
            'quote': sanitize_text(quote) if quote else '',
            'startTime': start_time_str,
            'endTime': end_time_str
        }
        # Save JSON file to the same output folder as the GIFs after each GIF is exported
        if output_dir:
            if config_title:
                json_filename = os.path.join(output_dir, f'gifs_metadata_{config_title}.json')
            else:
                json_filename = os.path.join(output_dir, 'gifs_metadata.json')
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(gif_metadata, f, indent=2, ensure_ascii=False)

def create_resized_gif(original_filename):
    resized_filename = original_filename.replace('.gif', '_resized.gif')
    if shutil.which("convert"):  # Check if ImageMagick's `convert` command is available
        try:
            subprocess.run(
                [
                    "convert", original_filename, "-coalesce", "-layers", "Optimize",
                    "-define", "optimize:extent=15360KB", resized_filename
                ],
                check=True
            )
            print(f"Resized GIF created: {resized_filename}")
        except subprocess.CalledProcessError as e:
            print(f"Error creating resized GIF: {e}")
    else:
        print("ImageMagick's `convert` command is not available. Skipping resized GIF creation.")

def reduce_resolution():
    global WIDTH, HEIGHT, PALLETSIZE, FRAME_DURATION
    # Only reduce resolution - never reduce framerate
    if WIDTH and HEIGHT:
        # Reduce resolution by 15% for gradual quality reduction
        WIDTH = max(int(WIDTH * 0.85), 320)
        HEIGHT = max(int(HEIGHT * 0.85), 180)
        print(f"New resolution: {WIDTH}x{HEIGHT}")
    # NEVER reduce palette - keep full 256 colors for best quality
    # PALLETSIZE = max(PALLETSIZE // 2, 64)  # Disabled - causes severe color banding
    # NEVER reduce framerate - keep original fps for smooth motion
    # FRAME_DURATION modification disabled

def regenerate_gif(images, filename):
    imageio.mimsave(filename, [array(img.resize((WIDTH, HEIGHT))) for img in images], palettesize=PALLETSIZE, duration=FRAME_DURATION, subrectangles=False)

def optimize_gif(filename, max_filesize_bytes, debug):
    ts_print(f"Optimizing GIF with ffmpeg palette...")
    optimize_start = datetime.now()
    iteration = 1
    temp_filename = filename.replace('.gif', f'_temp_{iteration}.gif')
    
    # HIGH QUALITY palette generation - prioritize color accuracy:
    # - palettegen=max_colors=256: use full 256 color palette
    # - palettegen=stats_mode=diff: analyze frame differences for better motion colors
    # - palettegen=reserve_transparent=0: don't reserve a color for transparency (no transparency needed)
    # - paletteuse=dither=floyd_steinberg: best quality dithering for natural gradients
    # - paletteuse=bayer_scale=5: fine bayer pattern for smooth color transitions
    # - paletteuse=diff_mode=none: render each frame fully (no transparency artifacts)
    # - -gifflags -offsetting: disable frame offsetting that can cause artifacts
    palette_filter = f"scale={WIDTH}:{HEIGHT}:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256:reserve_transparent=0:stats_mode=diff[p];[s1][p]paletteuse=dither=floyd_steinberg:diff_mode=none"
    
    subprocess.call([
        ffmpeg_path, '-i', filename, '-vf', palette_filter, '-gifflags', '-offsetting', '-r', f"{1 / FRAME_DURATION}", '-fs', str(max_filesize_bytes), '-y', temp_filename
    ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    while os.path.getsize(temp_filename) > max_filesize_bytes:
        iteration += 1
        new_temp_filename = filename.replace('.gif', f'_temp_{iteration}.gif')
        subprocess.call([
            ffmpeg_path, '-i', temp_filename, '-vf', palette_filter, '-gifflags', '-offsetting', '-r', f"{1 / FRAME_DURATION}", '-fs', str(max_filesize_bytes), '-y', new_temp_filename
        ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        if os.path.getsize(new_temp_filename) <= max_filesize_bytes:
            if debug:
                print(f"Optimization iteration {iteration}: {new_temp_filename} (size: {os.path.getsize(new_temp_filename)} bytes)")
            os.replace(new_temp_filename, filename)
            break
        else:
            if debug:
                print(f"Optimization iteration {iteration}: {new_temp_filename} (size: {os.path.getsize(new_temp_filename)} bytes)")
            os.remove(temp_filename)
            temp_filename = new_temp_filename

    # Log the final file size
    final_filesize = os.path.getsize(filename)
    final_filesize_mb = final_filesize / (1024 * 1024)
    ts_print(f"Final GIF size: {final_filesize_mb:.2f} MB (optimized in {(datetime.now() - optimize_start).total_seconds():.2f}s)")

    # Clean up temp files
    for file in os.listdir(os.path.dirname(filename)):
        if file.startswith(os.path.basename(filename).replace('.gif', '_temp_')):
            os.remove(os.path.join(os.path.dirname(filename), file))

def process_batch(root_folder, output_folder, video_extensions, gifs_args):
    """Process multiple video files across subfolders, preserving folder structure in output."""
    print(f"\n{'='*80}")
    print(f"BATCH PROCESSING MODE")
    print(f"Root folder: {root_folder}")
    print(f"Output folder: {output_folder}")
    print(f"Video extensions: {', '.join(video_extensions)}")
    print(f"{'='*80}\n")
    
    if not os.path.exists(root_folder):
        print(f"Error: Root folder does not exist: {root_folder}")
        return
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # Walk through all directories and find video files
    for dirpath, dirnames, filenames in os.walk(root_folder):
        # Get the relative path from root_folder
        rel_path = os.path.relpath(dirpath, root_folder)
        
        # Create corresponding output folder
        if rel_path == '.':
            episode_output_folder = output_folder
        else:
            episode_output_folder = os.path.join(output_folder, rel_path)
        
        if not os.path.exists(episode_output_folder):
            os.makedirs(episode_output_folder)
        
        # Process each video file in current directory
        for filename in filenames:
            # Check if file has valid video extension
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in video_extensions:
                continue
            
            video_path = os.path.join(dirpath, filename)
            
            print(f"\nProcessing: {os.path.relpath(video_path, root_folder)}")
            print(f"Output folder: {os.path.relpath(episode_output_folder, output_folder)}")
            
            try:
                # Call generate_gifs with the video file and episode-specific output folder
                generate_gifs(
                    video_path,
                    gifs_args.get('subtitles'),
                    episode_output_folder,
                    gifs_args.get('interval', 5),
                    gifs_args.get('startTime', '00:00:00'),
                    gifs_args.get('maxFilesize'),
                    gifs_args.get('debug', False),
                    gifs_args.get('randomTimes', False),
                    gifs_args.get('noHDR', False),
                    gifs_args.get('boostColors', 0),
                    gifs_args.get('boostFrameColors', 0),
                    gifs_args.get('quotes', True),
                    gifs_args.get('subtitleColor', 'white'),
                    gifs_args.get('subtitleSize'),
                    gifs_args.get('randomQuote', False),
                    gifs_args.get('saveJson', False),
                    gifs_args.get('checkHistory', False),
                    gifs_args.get('textBorder', 2),
                    gifs_args.get('uppercase', False),
                    gifs_args.get('italicize', False),
                    gifs_args.get('maxGifs'),
                    gifs_args.get('textPadding', 5),
                    gifs_args.get('bottomPadding'),
                    gifs_args.get('trailingPeriod', True),
                    gifs_args.get('outputBatchFolderSize'),
                    gifs_args.get('removeLeadingQuoteBracketWord', False),
                    gifs_args.get('configTitle'),
                    gifs_args.get('targetWidth')
                )
            except FileNotFoundError as e:
                # FileNotFoundError for screencaps is a critical error - stop the script
                print(f"\n{'='*80}")
                print(f"CRITICAL ERROR: Missing screencap file while processing {video_path}")
                print(f"Error: {e}")
                print(f"{'='*80}")
                print("\nThis error typically occurs when ffmpeg fails to extract frames.")
                print("The script will now stop. Please check:")
                print("  1. The video file is not corrupted")
                print("  2. There is enough disk space")
                print("  3. ffmpeg is working correctly")
                import traceback
                traceback.print_exc()
                raise  # Re-raise to stop the script
            except Exception as e:
                print(f"Error processing {video_path}: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    print(f"\n{'='*80}")
    print("BATCH PROCESSING COMPLETE")
    print(f"{'='*80}\n")

if __name__ == '__main__':

    def parse_filesize(v):
        """Parse file size string like '15mb', '15MB', '15 mb' to float MB."""
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            # Remove whitespace and convert to lowercase
            v = v.strip().lower()
            # Try to extract number and unit
            match = re.match(r'^([\d.]+)\s*(kb|mb|gb|b)?$', v)
            if match:
                number = float(match.group(1))
                unit = match.group(2) or 'mb'  # Default to MB if no unit specified
                if unit == 'kb':
                    return number / 1024.0
                elif unit == 'mb':
                    return number
                elif unit == 'gb':
                    return number * 1024.0
                elif unit == 'b':
                    return number / (1024.0 * 1024.0)
            else:
                # Try to parse as plain number
                try:
                    return float(v)
                except ValueError:
                    raise argparse.ArgumentTypeError(f'Invalid file size format: {v}. Use format like "15mb" or "15"')
        raise argparse.ArgumentTypeError(f'Invalid file size format: {v}. Use format like "15mb" or "15"')
    
    def str_to_bool(v):
        if isinstance(v, bool):
            return v
        if v.lower() in ('yes', 'true', 't', 'y', '1'):
            return True
        elif v.lower() in ('no', 'false', 'f', 'n', '0'):
            return False
        else:
            raise argparse.ArgumentTypeError('Boolean value expected.')

    def load_config_file(config_path):
        """Load settings from a .cfg config file."""
        config = configparser.ConfigParser()
        config.read(config_path)
        
        args_dict = {}
        
        # [batch_processing] section (new for multi-folder processing)
        if config.has_section('batch_processing'):
            if config.has_option('batch_processing', 'enabled'):
                args_dict['batchProcessingEnabled'] = str_to_bool(config.get('batch_processing', 'enabled'))
            # source_folder is where the video files are located
            if config.has_option('batch_processing', 'source_folder'):
                args_dict['batchSourceFolder'] = config.get('batch_processing', 'source_folder')
            # root_folder: when source_folder is set, this becomes the output folder
            # when source_folder is NOT set, this is the source folder (backwards compatibility)
            if config.has_option('batch_processing', 'root_folder'):
                root_folder = config.get('batch_processing', 'root_folder')
                if 'batchSourceFolder' in args_dict:
                    # source_folder is set, so root_folder becomes the output
                    args_dict['outputFolder'] = root_folder
                else:
                    # source_folder not set, use root_folder as source (legacy behavior)
                    args_dict['batchRootFolder'] = root_folder
            if config.has_option('batch_processing', 'output_folder'):
                args_dict['outputFolder'] = config.get('batch_processing', 'output_folder')
            if config.has_option('batch_processing', 'video_extensions'):
                extensions_str = config.get('batch_processing', 'video_extensions')
                # Parse comma-separated list and clean whitespace
                args_dict['batchVideoExtensions'] = [ext.strip() for ext in extensions_str.split(',')]
        
        # [movie] section
        if config.has_section('movie'):
            if config.has_option('movie', 'title'):
                args_dict['title'] = config.get('movie', 'title')
            if config.has_option('movie', 'path'):
                args_dict['movie'] = config.get('movie', 'path')
        
        # [batch_processing] section may also have title
        if config.has_section('batch_processing'):
            if config.has_option('batch_processing', 'title'):
                args_dict['title'] = config.get('batch_processing', 'title')
        
        # [gif_output] section (with [output] fallback for backwards compatibility)
        if config.has_section('gif_output'):
            if config.has_option('gif_output', 'folder'):
                args_dict['outputFolder'] = config.get('gif_output', 'folder')
        elif config.has_section('output'):
            if config.has_option('output', 'folder'):
                args_dict['outputFolder'] = config.get('output', 'folder')
        
        # [make_gifs] section (new organized structure)
        if config.has_section('make_gifs'):
            if config.has_option('make_gifs', 'max_filesize'):
                args_dict['maxFilesize'] = parse_filesize(config.get('make_gifs', 'max_filesize'))
            if config.has_option('make_gifs', 'save_json'):
                args_dict['saveJson'] = str_to_bool(config.get('make_gifs', 'save_json'))
            if config.has_option('make_gifs', 'batch_folder_size'):
                args_dict['outputBatchFolderSize'] = config.getint('make_gifs', 'batch_folder_size')
            if config.has_option('make_gifs', 'interval'):
                args_dict['interval'] = config.getint('make_gifs', 'interval')
            if config.has_option('make_gifs', 'start_time'):
                args_dict['startTime'] = config.get('make_gifs', 'start_time')
            if config.has_option('make_gifs', 'max_gifs'):
                args_dict['maxGifs'] = config.getint('make_gifs', 'max_gifs')
            if config.has_option('make_gifs', 'random_times'):
                args_dict['randomTimes'] = str_to_bool(config.get('make_gifs', 'random_times'))
            if config.has_option('make_gifs', 'random_quote'):
                args_dict['randomQuote'] = str_to_bool(config.get('make_gifs', 'random_quote'))
            if config.has_option('make_gifs', 'check_history'):
                args_dict['checkHistory'] = str_to_bool(config.get('make_gifs', 'check_history'))
            if config.has_option('make_gifs', 'remove_trailing_period'):
                # remove_trailing_period=true means trailing_period=false (invert the logic)
                args_dict['trailingPeriod'] = not str_to_bool(config.get('make_gifs', 'remove_trailing_period'))
            if config.has_option('make_gifs', 'target_width'):
                args_dict['targetWidth'] = config.getint('make_gifs', 'target_width')
        
        # [make_gifs.subtitles] section
        if config.has_section('make_gifs.subtitles'):
            if config.has_option('make_gifs.subtitles', 'path'):
                args_dict['subtitles'] = config.get('make_gifs.subtitles', 'path')
            if config.has_option('make_gifs.subtitles', 'track'):
                args_dict['subtitleTrack'] = config.getint('make_gifs.subtitles', 'track')
            if config.has_option('make_gifs.subtitles', 'color'):
                args_dict['subtitleColor'] = config.get('make_gifs.subtitles', 'color')
            if config.has_option('make_gifs.subtitles', 'size'):
                args_dict['subtitleSize'] = config.getint('make_gifs.subtitles', 'size')
            if config.has_option('make_gifs.subtitles', 'quotes'):
                args_dict['quotes'] = str_to_bool(config.get('make_gifs.subtitles', 'quotes'))
            if config.has_option('make_gifs.subtitles', 'uppercase'):
                args_dict['uppercase'] = str_to_bool(config.get('make_gifs.subtitles', 'uppercase'))
            if config.has_option('make_gifs.subtitles', 'italicize'):
                args_dict['italicize'] = str_to_bool(config.get('make_gifs.subtitles', 'italicize'))
            if config.has_option('make_gifs.subtitles', 'text_border'):
                args_dict['textBorder'] = config.getint('make_gifs.subtitles', 'text_border')
            if config.has_option('make_gifs.subtitles', 'text_padding'):
                args_dict['textPadding'] = config.getint('make_gifs.subtitles', 'text_padding')
            if config.has_option('make_gifs.subtitles', 'bottom_padding'):
                args_dict['bottomPadding'] = config.getint('make_gifs.subtitles', 'bottom_padding')
            if config.has_option('make_gifs.subtitles', 'trailing_period'):
                args_dict['trailingPeriod'] = str_to_bool(config.get('make_gifs.subtitles', 'trailing_period'))
            if config.has_option('make_gifs.subtitles', 'remove_leading_quote_bracket_word'):
                args_dict['removeLeadingQuoteBracketWord'] = str_to_bool(config.get('make_gifs.subtitles', 'remove_leading_quote_bracket_word'))
        
        # [make_gifs.video] section
        if config.has_section('make_gifs.video'):
            if config.has_option('make_gifs.video', 'no_hdr'):
                args_dict['noHDR'] = str_to_bool(config.get('make_gifs.video', 'no_hdr'))
            if config.has_option('make_gifs.video', 'boost_colors'):
                args_dict['boostColors'] = config.getint('make_gifs.video', 'boost_colors')
            if config.has_option('make_gifs.video', 'boost_frame_colors'):
                args_dict['boostFrameColors'] = config.getint('make_gifs.video', 'boost_frame_colors')
        
        # ========== LEGACY SUPPORT (backwards compatibility) ==========
        
        # Legacy [output] section options that were moved to [make_gifs]
        if config.has_section('output'):
            if config.has_option('output', 'max_filesize'):
                args_dict.setdefault('maxFilesize', parse_filesize(config.get('output', 'max_filesize')))
            if config.has_option('output', 'save_json'):
                args_dict.setdefault('saveJson', str_to_bool(config.get('output', 'save_json')))
            if config.has_option('output', 'batch_folder_size'):
                args_dict.setdefault('outputBatchFolderSize', config.getint('output', 'batch_folder_size'))
        
        # Legacy [subtitles] section
        if config.has_section('subtitles'):
            if config.has_option('subtitles', 'path'):
                args_dict.setdefault('subtitles', config.get('subtitles', 'path'))
            if config.has_option('subtitles', 'track'):
                args_dict.setdefault('subtitleTrack', config.getint('subtitles', 'track'))
            if config.has_option('subtitles', 'color'):
                args_dict.setdefault('subtitleColor', config.get('subtitles', 'color'))
            if config.has_option('subtitles', 'size'):
                args_dict.setdefault('subtitleSize', config.getint('subtitles', 'size'))
            if config.has_option('subtitles', 'quotes'):
                args_dict.setdefault('quotes', str_to_bool(config.get('subtitles', 'quotes')))
            if config.has_option('subtitles', 'uppercase'):
                args_dict.setdefault('uppercase', str_to_bool(config.get('subtitles', 'uppercase')))
            if config.has_option('subtitles', 'italicize'):
                args_dict.setdefault('italicize', str_to_bool(config.get('subtitles', 'italicize')))
            if config.has_option('subtitles', 'text_border'):
                args_dict.setdefault('textBorder', config.getint('subtitles', 'text_border'))
            if config.has_option('subtitles', 'text_padding'):
                args_dict.setdefault('textPadding', config.getint('subtitles', 'text_padding'))
            if config.has_option('subtitles', 'bottom_padding'):
                args_dict.setdefault('bottomPadding', config.getint('subtitles', 'bottom_padding'))
            if config.has_option('subtitles', 'trailing_period'):
                args_dict.setdefault('trailingPeriod', str_to_bool(config.get('subtitles', 'trailing_period')))
            if config.has_option('subtitles', 'remove_leading_quote_bracket_word'):
                args_dict.setdefault('removeLeadingQuoteBracketWord', str_to_bool(config.get('subtitles', 'remove_leading_quote_bracket_word')))
        
        # Legacy [generation] section
        if config.has_section('generation'):
            if config.has_option('generation', 'interval'):
                args_dict.setdefault('interval', config.getint('generation', 'interval'))
            if config.has_option('generation', 'start_time'):
                args_dict.setdefault('startTime', config.get('generation', 'start_time'))
            if config.has_option('generation', 'max_gifs'):
                args_dict.setdefault('maxGifs', config.getint('generation', 'max_gifs'))
            if config.has_option('generation', 'random_times'):
                args_dict.setdefault('randomTimes', str_to_bool(config.get('generation', 'random_times')))
            if config.has_option('generation', 'random_quote'):
                args_dict.setdefault('randomQuote', str_to_bool(config.get('generation', 'random_quote')))
            if config.has_option('generation', 'check_history'):
                args_dict.setdefault('checkHistory', str_to_bool(config.get('generation', 'check_history')))
        
        # Legacy [video] section
        if config.has_section('video'):
            if config.has_option('video', 'no_hdr'):
                args_dict.setdefault('noHDR', str_to_bool(config.get('video', 'no_hdr')))
            if config.has_option('video', 'boost_colors'):
                args_dict.setdefault('boostColors', config.getint('video', 'boost_colors'))
            if config.has_option('video', 'boost_frame_colors'):
                args_dict.setdefault('boostFrameColors', config.getint('video', 'boost_frame_colors'))
        
        return args_dict

    # Check if config file is provided (either as positional arg or --config)
    import sys
    config_args = {}
    config_path = None
    
    # Check for --config argument
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == '--config' and i < len(sys.argv) - 1:
            config_path = sys.argv[i + 1]
            break
        elif arg.startswith('--config='):
            config_path = arg.split('=', 1)[1]
            break
        elif arg.endswith('.cfg') and not arg.startswith('-'):
            config_path = arg
            break
    
    if config_path and os.path.exists(config_path):
        print(f"Loading config from: {config_path}")
        config_args = load_config_file(config_path)
        # Remove config-related args for argparse
        new_argv = [sys.argv[0]]
        skip_next = False
        for i, arg in enumerate(sys.argv[1:]):
            if skip_next:
                skip_next = False
                continue
            if arg == '--config':
                skip_next = True
                continue
            if arg.startswith('--config='):
                continue
            if arg.endswith('.cfg') and not arg.startswith('-'):
                continue
            new_argv.append(arg)
        sys.argv = new_argv

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, help='Path to .cfg config file')
    parser.add_argument('--movie', type=str, required=False, help='Path to the movie file (required for single-movie mode; not needed for batch processing mode)')
    parser.add_argument('--subtitles', type=str, help='Path to the subtitles file (optional)')
    parser.add_argument('--outputFolder', type=str, default=None, help='Output directory for GIFs. If relative path, creates folder in same directory as movie file.')
    parser.add_argument('--interval', type=int, default=5, help='Interval in seconds for GIF generation')
    parser.add_argument('--startTime', type=str, default="00:00:00", help='Start time for GIF generation in hh:mm:ss format')
    
    parser.add_argument('--maxFilesize', type=parse_filesize, help='Maximum file size for the GIF (e.g., "15mb", "15MB", "15")')
    parser.add_argument('--maxGifs', type=int, default=None, help='Maximum number of GIFs to generate before stopping (default: unlimited)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode to save each iteration of the optimization process')
    parser.add_argument('--randomTimes', action='store_true', help='Generate GIFs from different random start times')
    parser.add_argument('--noHDR', action='store_true', help='Remove HDR (convert to SDR) in GIFs')
    parser.add_argument('--boostColors', type=int, default=0, help='Boost color contrast/saturation by N percent')
    parser.add_argument('--boostFrameColors', type=int, default=0, help='Boost colors of each frame by N percent before making GIF')
    
    parser.add_argument('--quotes', type=str_to_bool, default=True, help='Whether to include quotes in GIFs (true/false)')
    parser.add_argument('--subtitleColor', type=str, default='white', help='Color of subtitle text (e.g., "yellow", "white", "red")')
    parser.add_argument('--subtitleSize', type=int, default=None, help='Size of subtitle text in pixels (default: 20px)')
    parser.add_argument('--randomQuote', action='store_true', help='Pick a random quote or random time. With --quotes true, picks a random quote. With --quotes false, picks a random time based on --interval')
    parser.add_argument('--saveJson', action='store_true', help='Save a JSON file with metadata for each generated GIF (filename, quote, startTime, endTime)')
    parser.add_argument('--checkHistory', action='store_true', help='Check existing JSON metadata and skip GIFs that have already been exported')
    parser.add_argument('--textBorder', type=int, default=2, help='Width of black border/stroke around text in pixels (default: 2)')
    parser.add_argument('--textPadding', type=int, default=5, help='Padding margin in pixels around text to prevent cropping (default: 5)')
    parser.add_argument('--bottomPadding', type=int, default=None, help='Padding from the bottom of the frame for the text in pixels (default: uses textPadding value)')
    parser.add_argument('--uppercase', action='store_true', help='Convert all text to uppercase')
    parser.add_argument('--italicize', action='store_true', default=False, help='Italicize the text (default: false)')
    parser.add_argument('--trailingPeriod', type=str_to_bool, default=True, help='Keep trailing periods in quotes (true/false). Set to false to remove trailing periods from all quotes (default: true)')
    parser.add_argument('--removeLeadingQuoteBracketWord', type=str_to_bool, default=False, help='Remove leading bracketed words from quotes like [Sommerville] or [whispers] (true/false, default: false)')
    parser.add_argument('--outputBatchFolderSize', type=int, default=None, help='Automatically organize GIFs into batch folders of specified size (e.g., 100). GIFs are saved directly into batch_001, batch_002, etc. folders as they are created (default: None, saves all GIFs in output folder)')
    parser.add_argument('--subtitleTrack', type=int, default=None, help='Specify which embedded subtitle track to use by index (use --listSubtitleTracks to see available tracks)')
    parser.add_argument('--listSubtitleTracks', action='store_true', help='List all available subtitle tracks in the video file and exit')
    args = parser.parse_args()

    # Merge config file settings with command line args (command line takes precedence)
    # For boolean options that have defaults, config file should override default values
    for key, value in config_args.items():
        if not hasattr(args, key) or getattr(args, key) is None:
            setattr(args, key, value)
        elif key == 'trailingPeriod' and key in config_args:
            # Special handling: config file should override default for trailingPeriod
            setattr(args, key, value)
        elif isinstance(getattr(args, key), bool) and not getattr(args, key):
            setattr(args, key, value)

    # Handle --listSubtitleTracks: list tracks and exit (single-movie mode only)
    if args.listSubtitleTracks:
        if not args.movie:
            print("Error: --listSubtitleTracks requires --movie argument")
            exit(1)
        tracks = get_subtitle_tracks(args.movie)
        if tracks:
            print("\nAvailable subtitle tracks:")
            print("="*60)
            for track in tracks:
                lang = track.get('language', 'unknown')
                title = track.get('title', '')
                codec = track.get('codec_name', 'unknown')
                index = track.get('index')
                display_title = f" - {title}" if title else ""
                print(f"  Track {index}: {lang}{display_title} ({codec})")
            print("="*60)
            print(f"\nUse --subtitleTrack <index> to select a specific track")
        else:
            print("No embedded subtitle tracks found in this video file.")
        exit(0)

    # If --subtitleTrack is specified, extract that track (single-movie mode only)
    subtitle_path_from_track = None
    
    # Print info about color boosting
    if args.boostFrameColors and args.boostFrameColors > 0:
        print(f"Boosting colors of each frame by {args.boostFrameColors}% before making GIFs.")

    # Check if batch processing is enabled
    if hasattr(args, 'batchProcessingEnabled') and args.batchProcessingEnabled:
        # Batch processing mode
        # Use source_folder for video files, fall back to root_folder for backwards compatibility
        source_folder = getattr(args, 'batchSourceFolder', None) or getattr(args, 'batchRootFolder', None)
        if not source_folder:
            print("Error: batch_processing enabled but source_folder (or root_folder) not specified in config")
            exit(1)
        
        # Use outputFolder from config (root_folder when source_folder is set), 
        # only fall back to source_folder + '_output' if not specified
        output_dir = getattr(args, 'outputFolder', None)
        if not output_dir:
            output_dir = source_folder + '_output'
        video_extensions = getattr(args, 'batchVideoExtensions', ['.mkv', '.mp4', '.avi', '.mov', '.flv', '.wmv', '.webm'])
        
        # Build gifs_args dict with all parameters for batch processing
        gifs_args = {
            'subtitles': getattr(args, 'subtitles', None),
            'interval': args.interval,
            'startTime': args.startTime,
            'maxFilesize': args.maxFilesize,
            'debug': args.debug,
            'randomTimes': args.randomTimes,
            'noHDR': args.noHDR,
            'boostColors': args.boostColors,
            'boostFrameColors': args.boostFrameColors,
            'quotes': args.quotes,
            'subtitleColor': args.subtitleColor,
            'subtitleSize': args.subtitleSize,
            'randomQuote': args.randomQuote,
            'saveJson': args.saveJson,
            'checkHistory': args.checkHistory,
            'textBorder': args.textBorder,
            'uppercase': args.uppercase,
            'italicize': args.italicize,
            'maxGifs': args.maxGifs,
            'textPadding': args.textPadding,
            'bottomPadding': args.bottomPadding,
            'trailingPeriod': args.trailingPeriod,
            'outputBatchFolderSize': args.outputBatchFolderSize,
            'removeLeadingQuoteBracketWord': getattr(args, 'removeLeadingQuoteBracketWord', False),
            'configTitle': getattr(args, 'title', None),
            'targetWidth': getattr(args, 'targetWidth', None)
        }
        
        process_batch(source_folder, output_dir, video_extensions, gifs_args)
    else:
        # Single movie mode (original behavior)
        if not args.movie:
            print("Error: No movie specified. Use --movie or --config with [movie] section")
            exit(1)
        
        # Handle subtitle track extraction for single-movie mode
        if args.subtitleTrack is not None and not args.subtitles:
            tracks = get_subtitle_tracks(args.movie)
            track_indices = [t['index'] for t in tracks]
            if args.subtitleTrack in track_indices:
                extracted_path = extract_subtitle_track(args.movie, args.subtitleTrack)
                if extracted_path:
                    subtitle_path_from_track = extracted_path
                    # Also save this preference for future runs
                    track_info = next((t for t in tracks if t['index'] == args.subtitleTrack), {})
                    save_subtitle_preference(args.movie, args.subtitleTrack, track_info)
            else:
                print(f"Error: Subtitle track {args.subtitleTrack} not found. Available tracks: {track_indices}")
                print("Use --listSubtitleTracks to see all available tracks.")
                exit(1)
        
        # If outputFolder is a relative path, make it relative to the movie's directory
        output_dir = args.outputFolder
        if output_dir is None:
            # Default to a 'gifs' folder in the same directory as the movie
            movie_dir = os.path.dirname(os.path.abspath(args.movie))
            output_dir = os.path.join(movie_dir, 'gifs')
        elif not os.path.isabs(output_dir):
            movie_dir = os.path.dirname(os.path.abspath(args.movie))
            output_dir = os.path.join(movie_dir, output_dir)

        generate_gifs(
            args.movie,
            subtitle_path_from_track or args.subtitles,
            output_dir,
            args.interval,
            args.startTime,
            args.maxFilesize,
            args.debug,
            args.randomTimes,
            args.noHDR,
            args.boostColors,
            args.boostFrameColors,
            args.quotes,
            args.subtitleColor,
            args.subtitleSize,
            args.randomQuote,
            args.saveJson,
            args.checkHistory,
            args.textBorder,
            args.uppercase,
            args.italicize,
            args.maxGifs,
            args.textPadding,
            args.bottomPadding,
            args.trailingPeriod,
            args.outputBatchFolderSize,
            getattr(args, 'removeLeadingQuoteBracketWord', False),
            getattr(args, 'title', None),
            getattr(args, 'targetWidth', None)
        )
