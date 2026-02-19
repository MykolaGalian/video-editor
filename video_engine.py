import os
import shutil
from typing import List, Optional
from models import Segment, ExportSettings, SourceClip

class FFmpegCommandBuilder:
    """
    Handles the generation of FFmpeg commands for video export.
    Independent of UI libraries (PyQt).
    """

    def __init__(self):
        self.ffmpeg_exec = self._find_ffmpeg()

    def _find_ffmpeg(self) -> Optional[str]:
        """
        Attempts to locate the ffmpeg executable.
        Checks system PATH and the current working directory.
        """
        # Check system PATH
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            return ffmpeg_path
        
        # Check current directory
        local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg
            
        return None

    def get_ffmpeg_path(self) -> Optional[str]:
        return self.ffmpeg_exec

    def set_ffmpeg_path(self, path: str):
        self.ffmpeg_exec = path

    def build_command(self, playlist: List[SourceClip], segments: List[Segment], settings: ExportSettings) -> List[str]:
        """
        Generates the FFmpeg command list based on playlist, segments and export settings.
        """
        if not self.ffmpeg_exec:
            raise FileNotFoundError("FFmpeg executable not found.")

        if not playlist:
             raise ValueError("No video clips in playlist.")

        if not segments:
             raise ValueError("No segments provided for export.")

        cmd = [self.ffmpeg_exec, "-y"]

        # --- INPUTS ---
        # Add all clips in playlist as inputs
        for clip in playlist:
            if not os.path.exists(clip.path):
                raise FileNotFoundError(f"Input file not found: {clip.path}")
            cmd.extend(["-i", clip.path])
        
        # Add external audio if needed
        idx_ext_audio = -1
        if settings.use_external_audio and settings.external_audio_path:
            if not os.path.exists(settings.external_audio_path):
                 raise FileNotFoundError(f"External audio file not found: {settings.external_audio_path}")
            cmd.extend(["-i", settings.external_audio_path])
            idx_ext_audio = len(playlist)

        # --- FILTER COMPLEX ---
        filter_parts = []
        concat_v_parts = []
        concat_a_parts = []
        
        # Iterate through Segments (Global Time) and map to Clips
        # A segment might span multiple clips.
        
        for seg_idx, seg in enumerate(segments):
            # Find intersection of seg with each clip
            for i, clip in enumerate(playlist):
                # Intersection of [seg.start, seg.end] and [clip.global_start, clip.global_end]
                start = max(seg.start_ms, clip.global_start_ms)
                end = min(seg.end_ms, clip.global_end_ms)
                
                if start < end:
                    # We have an overlap!
                    local_start = (start - clip.global_start_ms) / 1000.0
                    local_end = (end - clip.global_start_ms) / 1000.0
                    
                    # Video Trim + Scale + SetSAR
                    # We force scale to match the first clip's resolution to ensure all clips match
                    label_v = f"[v_seg_{seg_idx}_{i}]"
                    filter_parts.append(f"[{i}:v]trim={local_start}:{local_end},setpts=PTS-STARTPTS,scale={settings.width}:{settings.height},setsar=1{label_v}")
                    concat_v_parts.append(label_v)
                    
                    # Audio Trim (only if using original audio)
                    if not settings.use_external_audio:
                        label_a = f"[a_seg_{seg_idx}_{i}]"
                        filter_parts.append(f"[{i}:a]atrim={local_start}:{local_end},asetpts=PTS-STARTPTS{label_a}")
                        concat_a_parts.append(label_a)

        # Concat
        n_parts = len(concat_v_parts)
        if n_parts == 0:
             raise ValueError("No video content selected to export (segments might be out of range).")
             
        # Video Concat
        filter_parts.append(f"{''.join(concat_v_parts)}concat=n={n_parts}:v=1:a=0[outv]")
        map_v = "[outv]"
        
        # Audio Concat
        map_a = ""
        if settings.use_external_audio and settings.external_audio_path:
             # Use external audio
             map_a = f"{idx_ext_audio}:a"
             cmd.append("-shortest") # Cut audio to video length
        else:
             # Concat original audio parts
             filter_parts.append(f"{''.join(concat_a_parts)}concat=n={n_parts}:v=0:a=1[outa]")
             map_a = "[outa]"

        # Assemble Filter Complex
        cmd.extend(["-filter_complex", ";".join(filter_parts)])
        
        # MAPPING
        cmd.extend(["-map", map_v])
        cmd.extend(["-map", map_a])
        
        # Determine output format and codecs
        ext = os.path.splitext(settings.output_path)[1].lower()
        if not ext:
             ext = f".{settings.format}"

        mbps = settings.bitrate_mbps
        
        v_codec = 'libvpx-vp9'
        a_codec = 'libopus'
        extra_flags = []

        if ext == '.mkv':
            if settings.use_gpu:
                v_codec = 'hevc_nvenc'
                extra_flags = ['-b:v', f'{mbps}M', 
                               '-maxrate', f'{mbps + 5}M', 
                               '-bufsize', f'{mbps * 2}M', 
                               '-preset', 'p4', # p1-p7 for nvenc, p4 is medium
                               '-profile:v', 'main']
            else:
                v_codec = 'libvpx-vp9'
                extra_flags = ['-b:v', f'{mbps}M', 
                               '-maxrate', f'{mbps + 5}M', 
                               '-bufsize', f'{mbps * 2}M', 
                               '-crf', '30', 
                               '-deadline', 'realtime', 
                               '-cpu-used', '4']
            a_codec = 'libopus'
        elif ext == '.mp4':
            if settings.use_gpu:
                v_codec = 'h264_nvenc'
                extra_flags = ['-b:v', f'{mbps}M', 
                               '-maxrate', f'{mbps + 5}M', 
                               '-bufsize', f'{mbps * 2}M', 
                               '-preset', 'p4', 
                               '-profile:v', 'high',
                               '-pix_fmt', 'yuv420p']
            else:
                v_codec = 'libx264'
                extra_flags = ['-b:v', f'{mbps}M', 
                               '-maxrate', f'{mbps + 5}M', 
                               '-bufsize', f'{mbps * 2}M', 
                               '-preset', 'medium', 
                               '-pix_fmt', 'yuv420p']
            a_codec = 'aac'
        elif ext == '.webm':
            # Note: nvenc vp9 support is rare in standard ffmpeg builds
            # Fallback to libvpx-vp9 but use more cores if possible
            v_codec = 'libvpx-vp9'
            a_codec = 'libopus'
            extra_flags = ['-b:v', f'{mbps}M', 
                           '-maxrate', f'{mbps + 5}M', 
                           '-bufsize', f'{mbps * 2}M', 
                           '-crf', '30', 
                           '-deadline', 'realtime', 
                           '-cpu-used', '4']

        # Codec settings
        cmd.extend(["-c:v", v_codec])
        cmd.extend(extra_flags)
        
        # Audio Codec
        cmd.extend(["-c:a", a_codec])
        
        # FPS
        cmd.extend(["-r", str(settings.fps)])

        cmd.append(settings.output_path)

        return cmd
