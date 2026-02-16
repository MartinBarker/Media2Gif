#!/usr/bin/env python3
"""
Add AI-generated descriptions to GIF metadata using a local Ollama vision model.

Prerequisites:
1. Install Ollama: https://ollama.com/download
2. Pull a vision model: ollama pull llava:13b
3. Make sure Ollama is running: ollama serve
4. For face recognition: pip install face_recognition (requires dlib)

Usage:
    python add_gif_descriptions.py --folder "hard_boiled_gifs"
    python add_gif_descriptions.py --folder "hard_boiled_gifs" --model "llava:13b"
    python add_gif_descriptions.py --folder "hard_boiled_gifs" --skip-existing
    
    # With actor recognition (uses TMDB API - free):
    python add_gif_descriptions.py --folder "hard_boiled_gifs" --imdb-id "tt0104684"
"""

import os
import json
import base64
import argparse
import requests
from PIL import Image
import io
import sys

# Try to import face_recognition (optional dependency)
FACE_RECOGNITION_AVAILABLE = False
numpy_available = False

try:
    import numpy as np
    numpy_available = True
except ImportError:
    pass

if numpy_available:
    # Suppress the face_recognition_models error message
    _stderr = sys.stderr
    try:
        sys.stderr = open(os.devnull, 'w')
        import face_recognition
        sys.stderr = _stderr
        FACE_RECOGNITION_AVAILABLE = True
    except Exception as e:
        sys.stderr = _stderr
        # Silently fall back to AI-only detection
        FACE_RECOGNITION_AVAILABLE = False

# Load .env file if it exists
def load_dotenv():
    """Load environment variables from .env file if it exists."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and value:
                        os.environ.setdefault(key, value)

load_dotenv()

# ✅ Your Ollama supports /api/generate (your curl test proved it)
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

# TMDB API (free, just needs registration at https://www.themoviedb.org/)
TMDB_API_URL = "https://api.themoviedb.org/3"

REQUEST_TIMEOUT_SECONDS = 120


def extract_frame_from_gif(gif_path, frame_index=0):
    """Extract a frame from a GIF file and return as base64 JPEG."""
    try:
        with Image.open(gif_path) as img:
            # Use first frame for speed
            img.seek(frame_index)

            # Convert to RGB if necessary
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Save to bytes buffer
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            buffer.seek(0)

            return base64.b64encode(buffer.read()).decode("utf-8")
    except Exception as e:
        print(f"Error extracting frame from {gif_path}: {e}")
        return None


def extract_multiple_frames_from_gif(gif_path, num_frames=3):
    """Extract multiple frames from a GIF file for better actor recognition."""
    frames = []
    try:
        with Image.open(gif_path) as img:
            try:
                n_frames = img.n_frames
            except Exception:
                n_frames = 1
            
            # Get frames at different points (start, middle, end)
            if n_frames <= num_frames:
                frame_indices = list(range(n_frames))
            else:
                step = n_frames // num_frames
                frame_indices = [i * step for i in range(num_frames)]
            
            for idx in frame_indices:
                img.seek(idx)
                frame = img.copy()
                if frame.mode != "RGB":
                    frame = frame.convert("RGB")
                
                buffer = io.BytesIO()
                frame.save(buffer, format="JPEG", quality=85)
                buffer.seek(0)
                frames.append(base64.b64encode(buffer.read()).decode("utf-8"))
                
    except Exception as e:
        print(f"Error extracting frames from {gif_path}: {e}")
    return frames


# ============================================================================
# FACE RECOGNITION FUNCTIONS
# ============================================================================

def load_actor_face_encodings(actors):
    """
    Load face encodings for all actors from their downloaded images.
    Returns a dict mapping actor name to list of face encodings.
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return {}
    
    actor_encodings = {}
    
    for actor in actors:
        name = actor.get("name")
        image_paths = actor.get("local_image_paths", [])
        
        if not image_paths:
            continue
        
        encodings = []
        for img_path in image_paths:
            if not os.path.exists(img_path):
                continue
            try:
                img = face_recognition.load_image_file(img_path)
                face_encs = face_recognition.face_encodings(img)
                if face_encs:
                    # Take the first face found in each image
                    encodings.append(face_encs[0])
            except Exception as e:
                # Skip problematic images
                pass
        
        if encodings:
            actor_encodings[name] = encodings
    
    return actor_encodings


def detect_faces_in_frame(frame_image):
    """
    Detect faces in a PIL Image frame.
    Returns the number of faces and their encodings.
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return 0, []
    
    try:
        # Convert PIL Image to numpy array
        if hasattr(frame_image, 'mode'):
            if frame_image.mode != 'RGB':
                frame_image = frame_image.convert('RGB')
            img_array = np.array(frame_image)
        else:
            img_array = frame_image
        
        # Detect face locations
        face_locations = face_recognition.face_locations(img_array, model="hog")
        num_faces = len(face_locations)
        
        if num_faces == 0:
            return 0, []
        
        # Get face encodings
        face_encodings = face_recognition.face_encodings(img_array, face_locations)
        
        return num_faces, face_encodings
    except Exception as e:
        return 0, []


def identify_actors_by_face(gif_path, actor_encodings, max_frames=5, tolerance=0.55):
    """
    Identify actors in a GIF by comparing faces to known actor encodings.
    
    Args:
        gif_path: Path to the GIF file
        actor_encodings: Dict mapping actor names to list of face encodings
        max_frames: Maximum number of frames to analyze
        tolerance: Face matching tolerance (lower = stricter, 0.6 is default)
    
    Returns:
        tuple: (num_faces_detected, list of identified actor names)
    """
    if not FACE_RECOGNITION_AVAILABLE or not actor_encodings:
        return 0, []
    
    all_detected_faces = 0
    actor_matches = {}  # actor_name -> count of matches
    
    try:
        with Image.open(gif_path) as img:
            try:
                n_frames = img.n_frames
            except Exception:
                n_frames = 1
            
            # Sample frames evenly across the GIF
            if n_frames <= max_frames:
                frame_indices = list(range(n_frames))
            else:
                step = n_frames // max_frames
                frame_indices = [i * step for i in range(max_frames)]
            
            for idx in frame_indices:
                img.seek(idx)
                frame = img.copy()
                if frame.mode != "RGB":
                    frame = frame.convert("RGB")
                
                num_faces, face_encodings = detect_faces_in_frame(frame)
                all_detected_faces = max(all_detected_faces, num_faces)
                
                # Compare each detected face against known actors
                for face_encoding in face_encodings:
                    for actor_name, known_encodings in actor_encodings.items():
                        # Compare against all known encodings for this actor
                        matches = face_recognition.compare_faces(
                            known_encodings, face_encoding, tolerance=tolerance
                        )
                        if any(matches):
                            actor_matches[actor_name] = actor_matches.get(actor_name, 0) + 1
    
    except Exception as e:
        pass
    
    # Only include actors that were matched in multiple frames or with high confidence
    # Sort by match count and take actors that appear in at least 1 frame
    identified_actors = [
        name for name, count in sorted(actor_matches.items(), key=lambda x: -x[1])
        if count >= 1
    ]
    
    return all_detected_faces, identified_actors


def download_actor_images(actor_info, tmdb_movie_id, tmdb_api_key, actor_faces_folder):
    """
    Download 3 images for an actor:
    - 1 profile headshot
    - 2 images from the specific movie (tagged images or stills)
    """
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in actor_info["name"])
    actor_id = actor_info["tmdb_id"]
    downloaded_paths = []
    
    # 1. Download profile image (headshot)
    if actor_info.get("profile_path"):
        image_url = f"https://image.tmdb.org/t/p/w185{actor_info['profile_path']}"
        image_path = os.path.join(actor_faces_folder, f"{safe_name}_profile.jpg")
        
        if not os.path.exists(image_path):
            try:
                img_response = requests.get(image_url, timeout=10)
                img_response.raise_for_status()
                with open(image_path, 'wb') as f:
                    f.write(img_response.content)
                downloaded_paths.append(image_path)
            except Exception as e:
                print(f"      Warning: Could not download profile image for {actor_info['name']}: {e}")
        else:
            downloaded_paths.append(image_path)
    
    # 2. Try to get tagged images from this specific movie
    movie_images_count = 0
    try:
        # Get tagged images for this actor
        tagged_url = f"{TMDB_API_URL}/person/{actor_id}/tagged_images"
        params = {"api_key": tmdb_api_key}
        response = requests.get(tagged_url, params=params, timeout=10)
        response.raise_for_status()
        tagged_data = response.json()
        
        # Filter for images from this specific movie
        movie_images = []
        for img in tagged_data.get("results", []):
            media = img.get("media", {})
            if media.get("id") == tmdb_movie_id and img.get("file_path"):
                movie_images.append(img["file_path"])
        
        # Download up to 2 images from the movie
        for i, file_path in enumerate(movie_images[:2]):
            image_url = f"https://image.tmdb.org/t/p/w300{file_path}"
            image_path = os.path.join(actor_faces_folder, f"{safe_name}_movie_{i+1}.jpg")
            
            if not os.path.exists(image_path):
                try:
                    img_response = requests.get(image_url, timeout=10)
                    img_response.raise_for_status()
                    with open(image_path, 'wb') as f:
                        f.write(img_response.content)
                    downloaded_paths.append(image_path)
                    movie_images_count += 1
                except Exception:
                    pass
            else:
                downloaded_paths.append(image_path)
                movie_images_count += 1
                
    except Exception:
        pass
    
    # 3. If we couldn't get 2 movie images, try getting more profile images
    if movie_images_count < 2:
        try:
            # Get all profile images for this actor
            images_url = f"{TMDB_API_URL}/person/{actor_id}/images"
            params = {"api_key": tmdb_api_key}
            response = requests.get(images_url, params=params, timeout=10)
            response.raise_for_status()
            images_data = response.json()
            
            profiles = images_data.get("profiles", [])
            # Skip the first one (already downloaded as main profile)
            additional_needed = 2 - movie_images_count
            for i, profile in enumerate(profiles[1:additional_needed + 1]):
                if profile.get("file_path"):
                    image_url = f"https://image.tmdb.org/t/p/w185{profile['file_path']}"
                    image_path = os.path.join(actor_faces_folder, f"{safe_name}_alt_{i+1}.jpg")
                    
                    if not os.path.exists(image_path):
                        try:
                            img_response = requests.get(image_url, timeout=10)
                            img_response.raise_for_status()
                            with open(image_path, 'wb') as f:
                                f.write(img_response.content)
                            downloaded_paths.append(image_path)
                        except Exception:
                            pass
                    else:
                        downloaded_paths.append(image_path)
        except Exception:
            pass
    
    return downloaded_paths


def fetch_movie_cast_from_tmdb(imdb_id, tmdb_api_key, top_n=10, output_folder=None):
    """
    Fetch the top N cast members from TMDB using an IMDB ID.
    Downloads 3 actor images per actor for better face recognition.
    Returns a list of actor info dicts.
    """
    if not tmdb_api_key:
        print("Warning: No TMDB API key provided. Skipping actor recognition.")
        return [], None
    
    movie_info = None
    
    try:
        # First, find the TMDB movie ID from IMDB ID
        find_url = f"{TMDB_API_URL}/find/{imdb_id}"
        params = {
            "api_key": tmdb_api_key,
            "external_source": "imdb_id"
        }
        response = requests.get(find_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        movie_results = data.get("movie_results", [])
        if not movie_results:
            print(f"No movie found for IMDB ID: {imdb_id}")
            return [], None
        
        tmdb_movie_id = movie_results[0]["id"]
        movie_title = movie_results[0].get("title", "Unknown")
        movie_year = movie_results[0].get("release_date", "")[:4]
        
        movie_info = {
            "title": movie_title,
            "year": movie_year,
            "imdb_id": imdb_id,
            "tmdb_id": tmdb_movie_id
        }
        
        # Now fetch the credits
        credits_url = f"{TMDB_API_URL}/movie/{tmdb_movie_id}/credits"
        params = {"api_key": tmdb_api_key}
        response = requests.get(credits_url, params=params, timeout=10)
        response.raise_for_status()
        credits = response.json()
        
        cast = credits.get("cast", [])[:top_n]
        
        # Show movie info and first 5 actors for confirmation
        print(f"\n{'='*60}")
        print(f"TMDB API Result:")
        print(f"{'='*60}")
        print(f"Movie: {movie_title} ({movie_year})")
        print(f"IMDB ID: {imdb_id} | TMDB ID: {tmdb_movie_id}")
        print(f"\nTop cast members:")
        for i, actor in enumerate(cast[:5]):
            print(f"  {i+1}. {actor.get('name')} as {actor.get('character')}")
        if len(cast) > 5:
            print(f"  ... and {len(cast) - 5} more")
        print(f"{'='*60}")
        
        # Ask for confirmation
        while True:
            confirm = input("\nIs this the correct movie? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                print("✓ Confirmed. Proceeding with actor data...")
                break
            elif confirm in ['n', 'no']:
                print("✗ Cancelled. Please check your IMDB ID and try again.")
                return [], None
            else:
                print("Please enter 'y' or 'n'")
        
        actors = []
        
        # Create actor_faces folder if we need to download images
        actor_faces_folder = None
        if output_folder:
            actor_faces_folder = os.path.join(output_folder, "actor_faces")
            if not os.path.exists(actor_faces_folder):
                os.makedirs(actor_faces_folder)
        
        for actor in cast:
            actor_info = {
                "name": actor.get("name"),
                "character": actor.get("character"),
                "tmdb_id": actor.get("id"),
                "profile_path": actor.get("profile_path"),
            }
            
            # Download multiple actor images for better face recognition
            if actor_faces_folder:
                image_paths = download_actor_images(actor_info, tmdb_movie_id, tmdb_api_key, actor_faces_folder)
                actor_info["local_image_paths"] = image_paths
                img_count = len(image_paths)
            else:
                img_count = 0
            
            actors.append(actor_info)
            print(f"  - {actor_info['name']} as {actor_info['character']} ({img_count} images)")
        
        return actors, movie_info
        
    except Exception as e:
        print(f"Error fetching cast from TMDB: {e}")
        return [], None


def load_cached_movie_info(json_path):
    """Load cached movie and actor info from metadata JSON if available."""
    if not os.path.exists(json_path):
        return None, None
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        movie_info = metadata.get("_movie_info")
        actors = metadata.get("_actors")
        
        if movie_info and actors:
            return movie_info, actors
    except Exception:
        pass
    
    return None, None


def save_movie_info_to_metadata(json_path, movie_info, actors):
    """Save movie and actor info to metadata JSON for caching."""
    if not os.path.exists(json_path):
        metadata = {}
    else:
        with open(json_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    
    metadata["_movie_info"] = movie_info
    metadata["_actors"] = actors
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


class OllamaError(Exception):
    """Custom exception for Ollama API errors that should stop processing."""
    pass


def get_description_from_ollama(image_base64, model="llava:13b", actors=None):
    """
    Send image to Ollama vision model and get description via /api/generate.

    Returns:
        dict: {"description": str, "actors": list} on success
        None: On temporary/recoverable error
    Raises:
        OllamaError: On fatal errors (404, connection refused) that should stop processing
    """
    if actors:
        actor_names = [a["name"] for a in actors]
        actor_list = ", ".join(actor_names)
        prompt = f"""Analyze this image from a movie scene.

1. Describe what is happening in a short, concise phrase (5-15 words).
2. Identify which actors from this movie appear in this frame.

The movie's cast includes: {actor_list}

Respond in this EXACT format (no other text):
DESCRIPTION: [your description here]
ACTORS: [comma-separated list of actor names visible, or "none" if no faces visible]

Example response:
DESCRIPTION: Two men having an intense confrontation in a warehouse
ACTORS: Chow Yun-fat, Tony Leung"""
    else:
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
            "temperature": 0.3,
        },
    }

    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()

        # /api/generate returns text in "response"
        raw_response = (result.get("response") or "").strip()
        
        if actors:
            # Parse structured response
            description = ""
            detected_actors = []
            
            for line in raw_response.split("\n"):
                line = line.strip()
                if line.upper().startswith("DESCRIPTION:"):
                    description = line[12:].strip().strip('"\'')
                elif line.upper().startswith("ACTORS:"):
                    actors_str = line[7:].strip()
                    if actors_str.lower() != "none":
                        detected_actors = [a.strip() for a in actors_str.split(",") if a.strip()]
            
            # Validate actors against known cast
            valid_actor_names = [a["name"].lower() for a in actors]
            validated_actors = []
            for actor in detected_actors:
                # Check if detected actor matches any known actor (fuzzy match)
                for known in actors:
                    if actor.lower() in known["name"].lower() or known["name"].lower() in actor.lower():
                        validated_actors.append(known["name"])
                        break
            
            return {"description": description, "actors": list(set(validated_actors))}
        else:
            description = raw_response.strip('"\'')
            return {"description": description, "actors": []}

    except requests.exceptions.ConnectionError:
        raise OllamaError("Cannot connect to Ollama. Make sure Ollama is running (ollama serve).")
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise OllamaError(f"Ollama API endpoint not found (404). URL: {OLLAMA_GENERATE_URL}")
        if e.response is not None and e.response.status_code == 500:
            # Try to extract error details from response body
            error_detail = ""
            try:
                error_body = e.response.text
                if error_body:
                    error_detail = f"\nServer response: {error_body[:500]}"
            except:
                pass
            raise OllamaError(f"Ollama server error (500). The model may have crashed or run out of memory.{error_detail}")
        print(f"HTTP error from Ollama: {e}")
        return None
    except Exception as e:
        print(f"Error getting description from Ollama: {e}")
        return None


def check_ollama_available(model="llava:13b"):
    """Check if Ollama is running, /api/generate exists, and the model is available."""
    try:
        # 1) Confirm tags endpoint works (also confirms server is up)
        response = requests.get(OLLAMA_TAGS_URL, timeout=30)
        response.raise_for_status()

        models = response.json().get("models", [])
        available_names = [m.get("name", "") for m in models]

        # Model matching:
        # - If user passes "llava" we match any "llava:*"
        # - If user passes "llava:13b" we match exact
        want = model.strip()

        def model_exists(want_name: str) -> bool:
            if ":" in want_name:
                return want_name in available_names
            # no tag provided -> accept any variant of that base model
            return any(n.split(":")[0] == want_name for n in available_names)

        if not model_exists(want):
            print(f"Model '{want}' not found.")
            print(f"Available models: {available_names}")
            print(f"Pull the model with: ollama pull {want}")
            return False

        # 2) Sanity check: /api/generate should not 404
        # We do a cheap prompt-only call (no image) just to ensure route exists.
        # Use longer timeout since model may need to load into memory
        print("Warming up Ollama model (this may take a moment)...")
        sanity_payload = {"model": want, "prompt": "ping", "stream": False}
        sanity = requests.post(OLLAMA_GENERATE_URL, json=sanity_payload, timeout=120)
        if sanity.status_code == 404:
            print(f"Endpoint {OLLAMA_GENERATE_URL} returned 404 (unexpected on your system).")
            return False

        return True

    except requests.exceptions.ConnectionError:
        print("Ollama is not running. Start it with: ollama serve")
        return False
    except requests.exceptions.ReadTimeout:
        print("Ollama is taking too long to respond. The model may still be loading.")
        print("Try running 'ollama run llava:13b' in another terminal first to warm it up.")
        return False
    except Exception as e:
        print(f"Error checking Ollama: {e}")
        return False


def process_gifs_folder(folder_path, model="llava:13b", skip_existing=False, actors=None, movie_info=None, config_title=None, fresh_actors=False, fresh_descriptions=False):
    """Process all GIFs in a folder and add descriptions to metadata."""
    if not check_ollama_available(model):
        return

    # Use config_title in JSON filename if provided
    if config_title:
        json_path = os.path.join(folder_path, f"gifs_metadata_{config_title}.json")
    else:
        json_path = os.path.join(folder_path, "gifs_metadata.json")

    # Load existing metadata
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    else:
        # Also check for default gifs_metadata.json if config_title version not found
        default_json_path = os.path.join(folder_path, "gifs_metadata.json")
        if config_title and os.path.exists(default_json_path):
            print(f"Note: Using default gifs_metadata.json (config-specific file not found)")
            json_path = default_json_path
            with open(json_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        else:
            print(f"No {os.path.basename(json_path)} found in {folder_path}")
            metadata = {}
            for filename in os.listdir(folder_path):
                if filename.lower().endswith(".gif"):
                    metadata[filename] = {"quote": "", "startTime": "", "endTime": ""}

    # Erase actors/descriptions if fresh flags are set
    if fresh_actors or fresh_descriptions:
        fields_cleared = []
        if fresh_actors:
            fields_cleared.append("actors")
        if fresh_descriptions:
            fields_cleared.append("description")
        print(f"\n🗑️  Clearing fields from metadata: {', '.join(fields_cleared)}")
        
        for filename, data in metadata.items():
            if filename.startswith("_"):
                continue  # Skip metadata keys like _movie_info, _actors
            if fresh_actors and "actors" in data:
                data["actors"] = ""
            if fresh_descriptions and "description" in data:
                data["description"] = ""
        
        # Save the cleared metadata immediately
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"   ✓ Cleared {len([k for k in metadata if not k.startswith('_')])} entries")

    # Save movie info and actors to metadata for caching
    if movie_info:
        metadata["_movie_info"] = movie_info
    if actors:
        metadata["_actors"] = actors
    
    # Load face encodings for actors (if face_recognition is available)
    actor_encodings = {}
    if actors and FACE_RECOGNITION_AVAILABLE:
        print("\n🔍 Loading face encodings for actor recognition...")
        actor_encodings = load_actor_face_encodings(actors)
        if actor_encodings:
            print(f"   ✓ Loaded face data for {len(actor_encodings)} actors")
        else:
            print("   ⚠ No face encodings could be loaded from actor images")
    elif actors and not FACE_RECOGNITION_AVAILABLE:
        print("\n⚠ Face recognition not available (install with: pip install face_recognition)")
        print("   Falling back to AI-only actor detection")

    # Count only GIF entries (exclude metadata keys starting with _)
    gif_entries = {k: v for k, v in metadata.items() if not k.startswith("_")}
    total = len(gif_entries)
    processed = 0
    skipped = 0

    print(f"\nProcessing {total} GIFs in {folder_path}...")
    print(f"Using model: {model}")
    if actors:
        print(f"Actor recognition enabled: {len(actors)} cast members loaded")
    if skip_existing:
        # Count how many already have descriptions
        already_done = sum(1 for data in gif_entries.values() if data.get("description"))
        if already_done > 0:
            print(f"Skipping {already_done} GIFs that already have descriptions (use erase_previous=true to regenerate)")
    print("-" * 60)

    for filename, data in gif_entries.items():
        if skip_existing and data.get("description"):
            skipped += 1
            continue

        gif_path = os.path.join(folder_path, filename)

        # Check if GIF file exists (might be in a batch subfolder)
        if not os.path.exists(gif_path):
            for subfolder in os.listdir(folder_path):
                subfolder_path = os.path.join(folder_path, subfolder)
                if os.path.isdir(subfolder_path) and subfolder.startswith("batch_"):
                    potential_path = os.path.join(subfolder_path, filename)
                    if os.path.exists(potential_path):
                        gif_path = potential_path
                        break

        if not os.path.exists(gif_path):
            print(f"\n⚠ GIF not found: {filename}")
            continue

        processed += 1
        # Add blank line before each GIF for better readability
        print(f"\n[{processed}/{total}] Processing: {filename[:60]}...")
        print(f"    File: {gif_path}")

        image_base64 = extract_frame_from_gif(gif_path, frame_index=0)
        if not image_base64:
            continue

        try:
            result = get_description_from_ollama(image_base64, model, actors=actors)
        except OllamaError as e:
            print(f"\n❌ FATAL ERROR: {e}")
            print("Stopping processing.")
            return

        if result:
            data["description"] = result["description"]
            print(f"    → Description: {result['description']}")
            
            # Actor detection: combine AI detection with face recognition
            if actors:
                ai_detected_actors = set(result.get("actors", []))
                face_detected_actors = set()
                num_faces = 0
                
                # Use face recognition if available
                if actor_encodings:
                    num_faces, face_actors = identify_actors_by_face(
                        gif_path, actor_encodings, max_frames=5, tolerance=0.55
                    )
                    face_detected_actors = set(face_actors)
                    
                    if num_faces > 0:
                        print(f"    → Faces detected: {num_faces}")
                
                # Combine both detection methods
                # Face recognition is more reliable, so prioritize those matches
                all_detected = face_detected_actors.union(ai_detected_actors)
                
                # Filter to only include actors from our cast list
                valid_actor_names = {a["name"] for a in actors}
                validated_actors = [a for a in all_detected if a in valid_actor_names]
                
                if validated_actors:
                    data["actors"] = ", ".join(sorted(validated_actors))
                    # Show which method detected each actor
                    detection_details = []
                    for actor in sorted(validated_actors):
                        methods = []
                        if actor in face_detected_actors:
                            methods.append("face")
                        if actor in ai_detected_actors:
                            methods.append("AI")
                        detection_details.append(f"{actor} ({'+'.join(methods)})")
                    print(f"    → Actors identified: {', '.join(detection_details)}")
                else:
                    data["actors"] = ""
                    print(f"    → Actors identified: (none)")

            # Save after each update (in case of interruption)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        else:
            print("    → Failed to get description")

    print("-" * 60)
    print(f"Done! Processed: {processed}, Skipped: {skipped}")
    print(f"Metadata saved to: {json_path}")

import configparser
import sys

def load_config_file(config_path):
    """Load settings from a .cfg config file for add_gif_descriptions."""
    config = configparser.ConfigParser()
    config.read(config_path)
    
    args_dict = {}
    
    # [movie] section - get title and imdb_id
    if config.has_section('movie'):
        if config.has_option('movie', 'title'):
            args_dict['config_title'] = config.get('movie', 'title')
        if config.has_option('movie', 'imdb_id'):
            args_dict['imdb_id'] = config.get('movie', 'imdb_id')
    
    # [batch_processing] section (new for multi-folder processing)
    if config.has_section('batch_processing'):
        if config.has_option('batch_processing', 'enabled'):
            args_dict['batch_processing_enabled'] = config.get('batch_processing', 'enabled').lower() in ('yes', 'true', '1')
        if config.has_option('batch_processing', 'root_folder'):
            args_dict['batch_root_folder'] = config.get('batch_processing', 'root_folder')
        if config.has_option('batch_processing', 'output_folder'):
            args_dict['batch_output_folder'] = config.get('batch_processing', 'output_folder')
        # Also get title from batch_processing section if present
        if config.has_option('batch_processing', 'title'):
            args_dict['config_title'] = config.get('batch_processing', 'title')
    
    # [gif_output] section - get folder (with [output] fallback for backwards compatibility)
    if config.has_section('gif_output'):
        if config.has_option('gif_output', 'folder'):
            args_dict['folder'] = config.get('gif_output', 'folder')
    elif config.has_section('output'):
        if config.has_option('output', 'folder'):
            args_dict['folder'] = config.get('output', 'folder')
    
    # [add_gif_descriptions] section (new organized structure)
    if config.has_section('add_gif_descriptions'):
        if config.has_option('add_gif_descriptions', 'model'):
            args_dict['model'] = config.get('add_gif_descriptions', 'model')
        if config.has_option('add_gif_descriptions', 'erase_previous'):
            args_dict['erase_previous'] = config.get('add_gif_descriptions', 'erase_previous').lower() in ('yes', 'true', '1')
        if config.has_option('add_gif_descriptions', 'recognize_actors'):
            args_dict['recognize_actors'] = config.get('add_gif_descriptions', 'recognize_actors').lower() in ('yes', 'true', '1')
        if config.has_option('add_gif_descriptions', 'tmdb_api_key'):
            args_dict['tmdb_api_key'] = config.get('add_gif_descriptions', 'tmdb_api_key')
    
    # Legacy: [ai] section (backwards compatibility)
    if config.has_section('ai'):
        if config.has_option('ai', 'model') and 'model' not in args_dict:
            args_dict['model'] = config.get('ai', 'model')
        if config.has_option('ai', 'skip_existing') and 'erase_previous' not in args_dict:
            # Invert skip_existing to erase_previous (skip_existing=true means erase_previous=false)
            skip_existing = config.get('ai', 'skip_existing').lower() in ('yes', 'true', '1')
            args_dict['erase_previous'] = not skip_existing
        if config.has_option('ai', 'tmdb_api_key') and 'tmdb_api_key' not in args_dict:
            args_dict['tmdb_api_key'] = config.get('ai', 'tmdb_api_key')
    
    return args_dict


def process_batch(root_folder, model, skip_existing, actors, movie_info, recognize_actors=True, fresh_actors=False, fresh_descriptions=False):
    """Process multiple GIF folders recursively, preserving folder structure."""
    print(f"\n{'='*80}")
    print(f"BATCH PROCESSING MODE - Adding Descriptions")
    print(f"Root folder: {root_folder}")
    print(f"Model: {model}")
    if actors and recognize_actors:
        print(f"Actor recognition: Enabled ({len(actors)} cast members)")
    else:
        print(f"Actor recognition: Disabled")
    print(f"{'='*80}\n")
    
    if not os.path.exists(root_folder):
        print(f"Error: Root folder does not exist: {root_folder}")
        return
    
    # Walk through all directories and find gifs_metadata.json files
    folders_processed = 0
    for dirpath, dirnames, filenames in os.walk(root_folder):
        # Check if this directory contains gifs_metadata.json
        if 'gifs_metadata.json' in filenames:
            rel_path = os.path.relpath(dirpath, root_folder)
            print(f"\n{'='*60}")
            print(f"Processing folder: {rel_path}")
            print(f"{'='*60}")
            
            try:
                # Determine if we should use actors for this folder
                actors_to_use = actors if recognize_actors else None
                
                process_gifs_folder(dirpath, model, skip_existing, actors=actors_to_use, movie_info=movie_info, fresh_actors=fresh_actors, fresh_descriptions=fresh_descriptions)
                folders_processed += 1
            except Exception as e:
                print(f"Error processing {dirpath}: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    print(f"\n{'='*80}")
    print(f"BATCH PROCESSING COMPLETE - Processed {folders_processed} folders")
    print(f"{'='*80}\n")


def main():
    # Check if config file is provided (either as positional arg or --config)
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

    parser = argparse.ArgumentParser(
        description="Add AI-generated descriptions to GIF metadata using local Ollama vision model."
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to .cfg config file",
    )
    parser.add_argument(
        "--folder",
        required=not bool(config_args),
        help="Path to folder containing GIFs and gifs_metadata.json",
    )
    parser.add_argument(
        "--model",
        default="llava:13b",
        help="Ollama vision model to use (default: llava:13b). Examples: llava, llava:13b, llava:34b, bakllava",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip GIFs that already have descriptions (legacy, same as --no-erase)",
    )
    parser.add_argument(
        "--erase-previous",
        action="store_true",
        help="Erase and regenerate descriptions for GIFs that already have them (default: skip existing)",
    )
    parser.add_argument(
        "--imdb-id",
        help="IMDB ID of the movie (e.g., tt0104684 for Hard Boiled). Enables actor recognition.",
    )
    parser.add_argument(
        "--tmdb-api-key",
        help="TMDB API key for fetching cast info. Get free at https://www.themoviedb.org/settings/api",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force refresh of cached movie/actor info from TMDB",
    )
    parser.add_argument(
        "--freshActors",
        action="store_true",
        help="Erase all 'actors' fields in the JSON before processing",
    )
    parser.add_argument(
        "--freshDescriptions",
        action="store_true",
        help="Erase all 'description' fields in the JSON before processing",
    )

    args = parser.parse_args()

    # Merge config file settings with command line args (command line takes precedence)
    for key, value in config_args.items():
        arg_key = key.replace('-', '_')
        if not hasattr(args, arg_key) or getattr(args, arg_key) is None or (isinstance(getattr(args, arg_key), bool) and not getattr(args, arg_key)):
            setattr(args, arg_key, value)

    # Check if batch processing is enabled
    batch_mode = getattr(args, 'batch_processing_enabled', False)
    
    if batch_mode:
        # Batch processing mode - use root_folder
        root_folder = getattr(args, 'batch_root_folder', None)
        if not root_folder:
            print("Error: Batch processing enabled but batch_processing.root_folder not found in config")
            return
        if not os.path.exists(root_folder):
            print(f"Error: Root folder does not exist: {root_folder}")
            return
    else:
        # Single folder mode - original behavior
        if not args.folder:
            print("Error: --folder is required (or use a config file)")
            return

        if not os.path.exists(args.folder):
            print(f"Error: Folder not found: {args.folder}")
            return

    # Check for cached movie info first (only in single folder mode)
    config_title = getattr(args, 'config_title', None)
    if not batch_mode:
        if config_title:
            json_path = os.path.join(args.folder, f"gifs_metadata_{config_title}.json")
            # Fall back to default if config-specific file doesn't exist
            if not os.path.exists(json_path):
                default_json_path = os.path.join(args.folder, "gifs_metadata.json")
                if os.path.exists(default_json_path):
                    json_path = default_json_path
        else:
            json_path = os.path.join(args.folder, "gifs_metadata.json")
    else:
        json_path = None
    cached_movie_info, cached_actors = load_cached_movie_info(json_path) if json_path else (None, None)
    
    actors = None
    movie_info = None
    imdb_id = getattr(args, 'imdb_id', None)
    refresh_cache = getattr(args, 'refresh_cache', False)
    recognize_actors = getattr(args, 'recognize_actors', True)
    fresh_actors = getattr(args, 'freshActors', False)
    
    # --freshActors implies we should re-fetch movie/actor data from TMDB
    force_refetch = refresh_cache or fresh_actors
    
    # Use cached data if available and not forcing refresh
    if not recognize_actors:
        # Actor recognition explicitly disabled in config
        print("\nActor recognition disabled (recognize_actors=false)")
    elif cached_actors and cached_movie_info and not force_refetch:
        print(f"\n✓ Using cached movie info: {cached_movie_info.get('title', 'Unknown')} ({cached_movie_info.get('year', '')})")
        print(f"✓ Using cached actor data: {len(cached_actors)} cast members")
        print("  (use --refresh-cache or --freshActors to fetch fresh data from TMDB)")
        actors = cached_actors
        movie_info = cached_movie_info
    elif imdb_id:
        # Fetch from TMDB
        tmdb_api_key = getattr(args, 'tmdb_api_key', None) or os.environ.get("TMDB_API_KEY")
        if not tmdb_api_key:
            print("=" * 60)
            print("TMDB API KEY REQUIRED for actor recognition")
            print("=" * 60)
            print("To enable actor recognition, you need a free TMDB API key:")
            print("1. Sign up at https://www.themoviedb.org/signup")
            print("2. Go to https://www.themoviedb.org/settings/api")
            print("3. Request an API key (choose 'Developer' option)")
            print("4. Use it with: --tmdb-api-key YOUR_KEY")
            print("   Or set environment variable: export TMDB_API_KEY=YOUR_KEY")
            print("=" * 60)
            print("\nContinuing without actor recognition...\n")
        else:
            print(f"\nFetching cast for IMDB ID: {imdb_id}")
            # For batch mode, don't pass output_folder (actors will be fetched but not cached per-folder)
            output_folder_for_cache = args.folder if not batch_mode else None
            actors, movie_info = fetch_movie_cast_from_tmdb(imdb_id, tmdb_api_key, top_n=10, output_folder=output_folder_for_cache)
            if not actors:
                print("Warning: Could not fetch cast. Continuing without actor recognition.")

    # Determine if we should skip existing entries
    # erase_previous=True means regenerate, False means skip existing
    # Legacy: skip_existing=True means skip (same as erase_previous=False)
    erase_previous = getattr(args, 'erase_previous', False)
    skip_existing_legacy = getattr(args, 'skip_existing', False)
    
    # Default behavior is to skip existing (erase_previous=False)
    # Unless --erase-previous is specified
    skip_existing = not erase_previous
    
    # Legacy --skip-existing flag overrides (for backwards compatibility)
    if skip_existing_legacy:
        skip_existing = True

    # Get fresh flags
    fresh_actors = getattr(args, 'freshActors', False)
    fresh_descriptions = getattr(args, 'freshDescriptions', False)

    # Process folders based on mode
    if batch_mode:
        # Batch processing mode - use root_folder
        process_batch(root_folder, args.model, skip_existing, actors=actors, movie_info=movie_info, recognize_actors=recognize_actors, fresh_actors=fresh_actors, fresh_descriptions=fresh_descriptions)
    else:
        # Single folder mode
        process_gifs_folder(args.folder, args.model, skip_existing, actors=actors, movie_info=movie_info, config_title=config_title, fresh_actors=fresh_actors, fresh_descriptions=fresh_descriptions)


if __name__ == "__main__":
    main()
