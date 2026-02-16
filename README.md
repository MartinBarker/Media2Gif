

- Convert an entire movie or TV show to gifs
# make gifs

# add descriptions
- CLI args (fresh start)

# upload to giphy
- create giphy account / collection / fill out .env


________________
# Media-To-Gif

This script takes a movie file and subtitles file as input. It processes the movie to generate GIFs every 5 seconds. If a 5-second interval includes a quote, it generates a GIF of that full quote instead and overlays subtitles onto the GIF. The script downsamples, resizes, changes colors, and adjusts the framerate of the GIF to make it as close to 4MB as possible. The GIF is saved with a filename formatted as `${mediaName}-Start[${startTime}]-End[${endTime}]-Quote[${quote}].gif`, where the variables are:
- `mediaName`: Name of the movie/TV show, e.g., '28 days later'
- `startTime`: Start time formatted as `hh-mm-ss`
- `endTime`: End time formatted as `hh-mm-ss`
- `quote`: Quote (if any) on the screen, max 30 characters, sanitized to be only text with no other characters than a-z and 0-9.

## Setup Instructions

### Installing ffmpeg
The script requires `ffmpeg` to be installed on your system. Follow the instructions below to install `ffmpeg`:

#### macOS
1. Install `Homebrew` if you haven't already:
    ```sh
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    ```
2. Install `ffmpeg` using `Homebrew`:
    ```sh
    brew install ffmpeg
    ```

#### Linux
1. Install `ffmpeg` using your package manager. For example, on Ubuntu:
    ```sh
    sudo apt update
    sudo apt install ffmpeg
    ```

#### Windows
1. Download the `ffmpeg` release from the official website: https://ffmpeg.org/download.html
2. Extract the downloaded archive to a folder.
3. Add the `bin` folder from the extracted archive to your system's PATH environment variable.

### Setting up a Python Virtual Environment

#### macOS/Linux
1. Open a terminal.
2. Navigate to the project directory:
    ```sh
    cd /path/to/Media-To-Gif
    ```
3. Create a virtual environment:
    ```sh
    python3 -m venv venv
    ```
4. Activate the virtual environment:
    ```sh
    source venv/bin/activate
    ```
5. Install the required packages:
    ```sh
    pip install -r requirements.txt
    ```

#### Windows
1. Open Command Prompt or PowerShell.
2. Navigate to the project directory:
    ```sh
    cd C:\path\to\Media-To-Gif
    ```
3. Create a virtual environment:
    ```sh
    python -m venv venv
    ```
4. Activate the virtual environment:
    ```sh
    .\venv\Scripts\activate
    ```
5. Install the required packages:
    ```sh
    pip install -r requirements.txt
    ```

## Command Line Flags

```
--movie: Path to the movie file (required)
--subtitles: Path to the subtitles file (optional)
--outputFolder: Output directory for GIFs. If relative path, creates folder in same directory as movie file (default: /mnt/x/28dayslatergifs/)
--interval: Interval in seconds for GIF generation (default: 5)
--startTime: Start time for GIF generation in hh:mm:ss format (default: 00:00:00)
--maxFilesize: Maximum file size for the GIF (e.g., "15mb", "15MB", "15" for 15 megabytes)
--debug: Enable debug mode to save each iteration of the optimization process
--randomTimes: Generate GIFs from different random start times
--noHDR: Remove HDR (convert to SDR) in GIFs
--boostColors: Boost color contrast/saturation by N percent
--boostFrameColors: Boost colors of each frame by N percent before making GIF
--quotes: Whether to include quotes in GIFs (true/false) (default: true)
--subtitleColor: Color of subtitle text (e.g., "yellow", "white", "red") (default: white)
--subtitleSize: Size of subtitle text in pixels (default: 16)
--randomQuote: Pick a random quote or random time. With --quotes true, picks a random quote. With --quotes false, picks a random time based on --interval
--saveJson: Save a JSON file with metadata for each generated GIF (filename, quote, startTime, endTime)
--textBorder: Width of black border/stroke around text in pixels (default: 2)
--textPadding: Padding margin in pixels around text to prevent cropping (default: 5)
--bottomPadding: Padding from the bottom of the frame for the text in pixels (default: uses textPadding value)
--uppercase: Convert all text to uppercase
--italicize: Italicize the text (default: false)
--trailingPeriod: Keep trailing periods in quotes (true/false). Set to false to remove trailing periods from all quotes (default: true)
--outputBatchFolderSize: Automatically organize GIFs into batch folders of specified size (e.g., 100). GIFs are saved directly into batch_001, batch_002, etc. folders as they're created (default: None, saves all GIFs in output folder)
--subtitleTrack: Specify which embedded subtitle track to use by index (use --listSubtitleTracks to see available tracks)
--listSubtitleTracks: List all available subtitle tracks in the video file and exit
```

### Embedded Subtitle Track Selection
If no external subtitle file is provided, the script will automatically detect embedded subtitle tracks in the video file:
- If **multiple tracks** are found, you will be prompted to select which one to use
- If **one track** is found, it will be used automatically
- You can save your selection for future runs when prompted

To list available tracks without running the full script:
```sh
python make_gifs.py --movie "$movie_path" --listSubtitleTracks
```

To specify a track directly:
```sh
python make_gifs.py --movie "$movie_path" --subtitleTrack 2 --outputFolder "output"
```

## Running the Script
1. Ensure the virtual environment is activated.
2. Run the script with the required arguments:
    ```sh
    movie_path="/mnt/g/Miracle Mile (1988) [1080p]/Miracle.Mile.1988.1080p.BluRay.x264.YIFY.mp4"
    python make_gifs.py --movie "$movie_path" --outputFolder "/mnt/c/Users/marti/Documents/projects/Media-To-Gif/output" --interval 5
    ```
Example:
```sh
movie_path="/mnt/q/movies/28.Years.Later.2025.1080p.AMZN.WEB-DL.DDP5.1.H.264-KyoGo.mkv"
python make_gifs.py --movie "$movie_path" --outputFolder /mnt/x/28dayslatergifs --interval 5 --startTime 01:22:23 --maxFilesize 15mb
```

Example with Snake Eyes:
```sh
movie_path="/mnt/q/movies/Snake Eyes (1998)/Snake.Eyes.1998.1080p.BluRay.x264.YIFY.mp4"

# save gifs for random quotes and 5 second intervals in-between quotes (default interval = 5 seconds)
python make_gifs.py \
--movie "$movie_path" \
--outputFolder "gifs_only_quote" \
--quotes true \
--randomQuote \
--randomTimes \
--maxFilesize "15mb" \
--saveJson \
--checkHistory

# save gifs for only random quotes - no non-quote output gifs
python make_gifs.py \
--movie "$movie_path" \
--outputFolder "gifs_only_quote_15mb" \
--quotes true \
--randomQuote \
--maxFilesize "15mb" \
--saveJson

# save gifs for only random non-quotes - no quotes in gif - random times
python make_gifs.py \
--movie "$movie_path" \
--outputFolder "gifs_only_quote" \
--quotes false \
--randomQuote
```

## finale 
movie_path="/mnt/q/movies/28 Years Later (2025) (2160p iT WEB-DL H265 HDR10+ DDP Atmos 5.1 English - HONE).mkv"
./venv/bin/python make_gifs.py --movie "$movie_path" --outputFolder /mnt/q/movies/1080p --interval 5 --startTime 01:48:00 --maxFilesize 55
```

The script will generate GIFs and save them in the specified output folder.


# Test command
```
movie_path="/mnt/q/movies/Heat (1995) [1080p]/Heat.1995.1080p.BRrip.x264.YIFY.mp4"
python make_gifs.py \
--movie "$movie_path" \
--outputFolder "gif_output" \
--quotes true \
--randomQuote \
--randomTimes \
--maxFilesize "15mb" \
--saveJson \
--checkHistory \
--subtitleColor "white" \
--subtitleSize 45 \
--textBorder 3 \
--textPadding 15 \
--uppercase \
--randomQuote \
--randomTimes \
--maxGifs 10
```

# Generate gif from entire movie
```
movie_path="/mnt/q/movies/Heat (1995) [1080p]/Heat.1995.1080p.BRrip.x264.YIFY.mp4"
python make_gifs.py \
--movie "$movie_path" \
--outputFolder "entire_movie_gifs" \
--maxFilesize "15mb" \
--quotes true \
--saveJson \
--subtitleColor "white" \
--subtitleSize 35 \
--textBorder 3 \
--textPadding 15 \
--bottomPadding 20 \
--uppercase
```


movie_path="/mnt/q/movies/Heat (1995) [1080p]/Heat.1995.1080p.BRrip.x264.YIFY.mp4"
subtitle_path="/mnt/q/movies/Heat (1995) [1080p]/Heat.1995.1080p.BRrip.x264.YIFY.srt"
python make_gifs.py \
--movie "$movie_path" \
--subtitles "$subtitle_path" \
--outputFolder "entire_movie_gifs" \
--maxFilesize "15mb" \
--quotes true \
--saveJson \
--subtitleColor "white" \
--subtitleSize 35 \
--textBorder 3 \
--textPadding 15 \
--bottomPadding 20 \
--uppercase 


```Avatar

movie_path="/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/Avatar.The.Way.Of.Water.2022.1080p.WEBRip.x264.AAC5.1-[YTS.MX].mp4"
subtitle_path="/mnt/q/movies/Avatar The Way Of Water (2022) [1080p] [WEBRip] [5.1] [YTS.MX]/Avatar.The.Way.Of.Water.2022.1080p.WEBRip.x264.AAC5.1-[YTS.MX].srt"

python make_gifs.py \
--movie "$movie_path" \
--subtitles "$subtitle_path" \
--outputFolder "entire_movie_gifs" \
--maxFilesize "15mb" \
--quotes true \
--saveJson \
--subtitleColor "white" \
--subtitleSize 35 \
--textBorder 3 \
--textPadding 15 \
--bottomPadding 20 \
--uppercase \
--trailingPeriod false \
--outputBatchFolderSize 100

```

# Hard Boiled - 20 random quote gifs
```
movie_path="/mnt/q/movies/Hard Boiled (1992)/Hard.Boiled.1992.1080p.BluRay.x265.hevc.10bit.AAC.5.1.commentary-HeVK.mkv"

python make_gifs.py \
--movie "$movie_path" \
--subtitleTrack 5 \
--outputFolder "/mnt/c/Users/marti/Documents/projects/Media-To-Gif/hard_boiled_gifs_no_transperancy" \
--maxFilesize "15mb" \
--quotes true \
--saveJson \
--subtitleColor "white" \
--subtitleSize 35 \
--textBorder 3 \
--textPadding 15 \
--bottomPadding 20 \
--uppercase
```