import os
from PIL import Image
from numpy import array
import imageio

GIF_DIR = '/mnt/c/Users/marti/Desktop'
MAX_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB in bytes

def resize_gif_python(gif_path):
    # Initial parameters
    width, height = None, None
    palettesize = 256

    # Load GIF frames
    try:
        gif = Image.open(gif_path)
    except Exception as e:
        print(f"Error opening {gif_path}: {e}")
        return

    frames = []
    try:
        while True:
            frame = gif.convert("RGB")
            frames.append(frame)
            gif.seek(gif.tell() + 1)
    except EOFError:
        pass

    # Use original size
    width, height = frames[0].size

    # Output path
    resized_path = gif_path.replace('.gif', '_resized.gif')

    # Iteratively reduce resolution and palette size
    while True:
        # Resize frames if needed
        resized_frames = [frame.resize((width, height)) for frame in frames]
        # Save GIF
        imageio.mimsave(resized_path, [array(f) for f in resized_frames], palettesize=palettesize, duration=0.1, loop=0)
        filesize = os.path.getsize(resized_path)
        print(f"Resized: {gif_path} -> {resized_path} ({filesize} bytes)")
        if filesize <= MAX_SIZE_BYTES or (width <= 320 or height <= 180 or palettesize <= 32):
            break
        # Reduce resolution and palette size
        width = max(width // 2, 320)
        height = max(height // 2, 180)
        palettesize = max(palettesize // 2, 32)
        print(f"Reducing to {width}x{height}, palettesize={palettesize}")

def main():
    print(f"Resizing all GIFs in {GIF_DIR} to be under 15MB using Python...")
    for fname in os.listdir(GIF_DIR):
        if fname.lower().endswith('.gif'):
            gif_path = os.path.join(GIF_DIR, fname)
            resize_gif_python(gif_path)

if __name__ == '__main__':
    main()
