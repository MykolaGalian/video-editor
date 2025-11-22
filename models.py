from dataclasses import dataclass
from typing import Optional

@dataclass
class Segment:
    """Class representing a video segment to keep."""
    start_ms: int
    end_ms: int

@dataclass
class ExportSettings:
    """Class representing export settings."""
    output_path: str
    format: str  # 'mp4', 'webm', 'mkv'
    bitrate_mbps: int
    use_external_audio: bool = False
    external_audio_path: Optional[str] = None
    append_video_path: Optional[str] = None
