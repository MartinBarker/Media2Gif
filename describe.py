#!/usr/bin/env python3
"""
Core AI description module for GIF files using Ollama vision models.

Shared by add_gif_descriptions.py (batch) and make_gifs.py (inline --describe).
"""

import os
import json
import base64
import io
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import requests

OLLAMA_API_URL = "http://localhost:11434/api/generate"


class OllamaFatalError(Exception):
    """Raised when Ollama returns an unrecoverable error (404, connection refused, etc.)."""
    pass


def print_ollama_setup_guide(model="llava"):
    """Print a step-by-step guide for getting Ollama running locally."""
    print()
    print("=" * 64)
    print("  Ollama Setup Guide")
    print("=" * 64)
    print()
    print("  Ollama is a free, local AI runtime that runs vision models")
    print("  on your machine. No API keys or internet needed after setup.")
    print()
    print("  1. INSTALL Ollama")
    print("     Linux / WSL:  curl -fsSL https://ollama.com/install.sh | sh")
    print("     macOS:        brew install ollama")
    print("     Windows:      https://ollama.com/download")
    print()
    print(f"  2. PULL a vision model (you need: {model})")
    print(f"     ollama pull {model}")
    print()
    print("     Other vision models you can try:")
    print("       ollama pull llava          (7B  - fast, ~4 GB)")
    print("       ollama pull llava:13b      (13B - better, ~8 GB)")
    print("       ollama pull llava:34b      (34B - best, ~20 GB)")
    print("       ollama pull bakllava       (7B  - alternative)")
    print()
    print("  3. START the Ollama server")
    print("     ollama serve")
    print()
    print("     Keep this running in a separate terminal while making GIFs.")
    print()
    print("  4. VERIFY it works")
    print("     curl http://localhost:11434/api/tags")
    print(f"     (should list '{model}' in the response)")
    print()
    print("  5. RE-RUN your command")
    print("     python make_gifs.py F1.cfg --describe")
    print()
    print("=" * 64)
    print()


def extract_frame_from_gif(gif_path, frame_index=None):
    """Extract a frame from a GIF and return it as a base64 JPEG string."""
    try:
        with Image.open(gif_path) as img:
            n_frames = getattr(img, 'n_frames', 1)
            if frame_index is None:
                frame_index = n_frames // 2
            img.seek(min(frame_index, n_frames - 1))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=85)
            buf.seek(0)
            return base64.b64encode(buf.read()).decode('utf-8')
    except Exception as e:
        print(f"Error extracting frame from {gif_path}: {e}")
        return None


def get_description_from_ollama(image_base64, model="llava"):
    """Send an image to Ollama and return a short scene description."""
    prompt = (
        "Describe what is happening in this image in a short, concise phrase "
        "(5-15 words). Focus on the main action or scene. Examples:\n"
        '- "man pointing gun at another person"\n'
        '- "woman running through rain"\n'
        '- "car exploding in street"\n'
        '- "two people having intense conversation"\n\n'
        "Respond with ONLY the description, nothing else."
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_base64],
        "stream": False,
        "options": {"temperature": 0.3},
    }
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get('response', '').strip().strip('"\'')
    except requests.exceptions.ConnectionError as e:
        raise OllamaFatalError(f"Cannot connect to Ollama. Make sure it is running (ollama serve): {e}")
    except requests.exceptions.HTTPError as e:
        raise OllamaFatalError(f"Ollama HTTP error (model may not exist): {e}")
    except Exception as e:
        print(f"Warning: Ollama description error: {e}")
        return None


def check_ollama_available(model="llava"):
    """Return True if Ollama is running and the model can generate."""
    # Step 1: check if Ollama is reachable
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get('models', [])
        model_names = [m.get('name', '').split(':')[0] for m in models]
        if model.split(':')[0] not in model_names:
            print(f"Model '{model}' not found. Available models: {model_names}")
            print_ollama_setup_guide(model)
            return False
    except requests.exceptions.ConnectionError:
        print("Ollama is not running or not installed.")
        print_ollama_setup_guide(model)
        return False
    except Exception as e:
        print(f"Error checking Ollama: {e}")
        print_ollama_setup_guide(model)
        return False

    # Step 2: do a real test call to confirm the model works
    print(f"Testing Ollama model '{model}'... ", end="", flush=True)
    try:
        test_payload = {
            "model": model,
            "prompt": "Say OK",
            "stream": False,
            "options": {"num_predict": 5},
        }
        test_resp = requests.post(OLLAMA_API_URL, json=test_payload, timeout=60)
        test_resp.raise_for_status()
        print("OK!")
        return True
    except requests.exceptions.HTTPError as e:
        print("FAILED!")
        print(f"Model '{model}' is listed but cannot generate: {e}")
        print_ollama_setup_guide(model)
        return False
    except Exception as e:
        print("FAILED!")
        print(f"Test generation failed: {e}")
        print_ollama_setup_guide(model)
        return False


def describe_gif(gif_path, model="llava"):
    """Extract the middle frame of a GIF and describe it. Returns str or None.

    Raises OllamaFatalError on unrecoverable Ollama failures.
    """
    image_base64 = extract_frame_from_gif(gif_path)
    if not image_base64:
        return None
    return get_description_from_ollama(image_base64, model)


def get_system_load():
    """Return estimated CPU usage as a percentage (0-100)."""
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except ImportError:
        pass
    try:
        load_1min = os.getloadavg()[0]
        cpus = os.cpu_count() or 1
        return min(100.0, (load_1min / cpus) * 100)
    except (OSError, AttributeError):
        return 50.0


def find_gif_path(filename, folder_path):
    """Locate a GIF file in folder_path, checking batch subfolders if needed."""
    direct = os.path.join(folder_path, filename)
    if os.path.exists(direct):
        return direct
    try:
        for sub in os.listdir(folder_path):
            sub_path = os.path.join(folder_path, sub)
            if os.path.isdir(sub_path) and sub.startswith('batch_'):
                candidate = os.path.join(sub_path, filename)
                if os.path.exists(candidate):
                    return candidate
    except OSError:
        pass
    return None


class AdaptiveDescriber:
    """Background GIF describer that adapts concurrency to system load.

    Usage::

        describer = AdaptiveDescriber(model, json_path, metadata_dict)
        describer.describe_undescribed(folder)   # backfill existing
        describer.submit(gif_path, filename)     # queue new
        describer.shutdown()                      # wait & cleanup
    """

    def __init__(self, model="llava", json_path=None, metadata=None, max_workers=None):
        self.model = model
        self.json_path = json_path
        self.metadata = metadata if metadata is not None else {}
        cpus = os.cpu_count() or 2
        self.max_workers = max_workers or max(1, min(cpus // 2, 4))
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=self.max_workers)
        self._futures = []
        self.described_count = 0
        self.failed_count = 0
        self.fatal_error = None

    def _do_describe(self, gif_path, filename):
        """Worker: describe one GIF, throttle when system is busy."""
        if self.fatal_error:
            return None

        load = get_system_load()
        if load > 85:
            time.sleep(3)
        elif load > 70:
            time.sleep(1)

        try:
            description = describe_gif(gif_path, self.model)
        except OllamaFatalError as e:
            with self._lock:
                if not self.fatal_error:
                    self.fatal_error = str(e)
                    print(f"\n*** FATAL: {e}")
                    print("*** Stopping all AI descriptions.")
                    print_ollama_setup_guide(self.model)
            return None

        with self._lock:
            if description:
                if filename in self.metadata:
                    self.metadata[filename]['description'] = description
                else:
                    self.metadata[filename] = {'description': description}
                self.described_count += 1
                print(f"  [describe] {filename[:60]} -> {description}")
            else:
                self.failed_count += 1
                print(f"  [describe] {filename[:60]} -> FAILED")

            if self.json_path:
                try:
                    with open(self.json_path, 'w', encoding='utf-8') as f:
                        json.dump(self.metadata, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

        return description

    def submit(self, gif_path, filename):
        """Queue a GIF for background description. No-ops after a fatal error."""
        if self.fatal_error:
            return None
        future = self._pool.submit(self._do_describe, gif_path, filename)
        self._futures.append(future)
        return future

    def describe_undescribed(self, folder_path):
        """Find existing GIFs that lack descriptions and queue them all."""
        undescribed = []
        for filename, data in list(self.metadata.items()):
            if data.get('description'):
                continue
            gif_path = find_gif_path(filename, folder_path)
            if gif_path:
                undescribed.append((gif_path, filename))

        if not undescribed:
            print("All existing GIFs already have descriptions.")
            return

        print(f"Found {len(undescribed)} undescribed GIFs. Queuing for description...")
        for gif_path, filename in undescribed:
            self.submit(gif_path, filename)

    def check_fatal(self):
        """If a fatal error occurred, raise SystemExit immediately."""
        if self.fatal_error:
            self._pool.shutdown(wait=False, cancel_futures=True)
            raise SystemExit(f"Exiting due to Ollama error: {self.fatal_error}")

    def wait(self):
        """Block until every pending description finishes."""
        for future in self._futures:
            try:
                future.result()
            except Exception:
                pass
        self._futures.clear()

    def shutdown(self):
        """Wait for remaining work, print summary, and close the pool.

        Raises SystemExit if a fatal Ollama error occurred.
        """
        self.wait()
        self._pool.shutdown(wait=True)
        if self.described_count > 0 or self.failed_count > 0:
            print(f"\nDescription summary: {self.described_count} described, {self.failed_count} failed")
        if self.fatal_error:
            raise SystemExit(f"Exiting due to Ollama error: {self.fatal_error}")
