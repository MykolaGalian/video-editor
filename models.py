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
    width: int
    height: int
    use_external_audio: bool = False
    external_audio_path: Optional[str] = None
    fps: float = 23.976
    use_gpu: bool = False

@dataclass
class SourceClip:
    """Class representing a source video file in the timeline."""
    path: str
    duration_ms: int
    width: int
    height: int
    global_start_ms: int = 0
    global_end_ms: int = 0
