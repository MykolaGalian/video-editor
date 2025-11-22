# Open 4K Video Editor

A simple yet powerful video editor built with Python and PyQt6, designed for fast trimming and appending of 4K video files.

## Requirements

- **Python 3.10+**
- **FFmpeg & FFprobe**:
    - The application requires `ffmpeg.exe` and `ffprobe.exe` to be present.
    - Place these executables in the root directory of the application (next to `main.py` or the `.exe`).
    - Alternatively, you will be prompted to select the `ffmpeg.exe` path when exporting.

## Installation

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install PyQt6
   ```
3. Download FFmpeg build (essentials) and extract `ffmpeg.exe` and `ffprobe.exe` to the project folder.

## Usage

Run the application:
```bash
python main.py
```

### Workflow
1. **Load Video**: Opens a file and starts a new timeline.
2. **Add Clip**: Appends more videos to the existing timeline.
3. **Edit**: The timeline represents all clips stitched together. You can cut/trim anywhere across file boundaries.


### Features
- **Virtual Global Timeline**: Edit multiple video files as a single continuous sequence.
- **Trimming**: Select "Keep Selected" or "Remove Selected" segments across the entire timeline.
- **Appending**: Add clips to the timeline at any time.
- **External Audio**: Replace the audio track for the entire project.
- **Smart Player**: Skips over removed segments during preview.
- **Real-time Duration**: See the exact length of your final video.
