from typing import List, Tuple, Optional
from models import SourceClip

class TimelineManager:
    """
    Manages the global timeline consisting of multiple source clips.
    Handles coordinate conversion between Global Time and Local Clip Time.
    """
    def __init__(self):
        self.playlist: List[SourceClip] = []

    def add_clip(self, path: str, duration_ms: int, width: int, height: int):
        """Adds a clip to the end of the playlist."""
        global_start = 0
        if self.playlist:
            global_start = self.playlist[-1].global_end_ms
        
        global_end = global_start + duration_ms
        clip = SourceClip(path, duration_ms, width, height, global_start, global_end)
        self.playlist.append(clip)

    def get_total_duration(self) -> int:
        """Returns the total duration of the timeline in milliseconds."""
        if not self.playlist:
            return 0
        return self.playlist[-1].global_end_ms

    def get_clip_at_global_time(self, global_ms: int) -> Tuple[Optional[SourceClip], int]:
        """
        Finds the clip at the given global time.
        Returns (SourceClip, local_ms).
        If time is out of bounds, returns (None, 0) or (LastClip, End) depending on logic.
        """
        if not self.playlist:
            return None, 0

        # Clamp to bounds
        if global_ms < 0:
            global_ms = 0
        if global_ms >= self.get_total_duration():
            return None, 0 # Or handle end of stream

        for clip in self.playlist:
            if clip.global_start_ms <= global_ms < clip.global_end_ms:
                local_ms = global_ms - clip.global_start_ms
                return clip, local_ms
        
        return None, 0

    def get_next_clip(self, current_clip: SourceClip) -> Optional[SourceClip]:
        """Returns the next clip in the playlist after the given one."""
        try:
            idx = self.playlist.index(current_clip)
            if idx + 1 < len(self.playlist):
                return self.playlist[idx + 1]
        except ValueError:
            pass
        return None

    def clear(self):
        self.playlist = []
