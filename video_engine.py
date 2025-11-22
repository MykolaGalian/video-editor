import os
import shutil
from typing import List, Optional
from models import Segment, ExportSettings

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

    def build_command(self, input_path: str, segments: List[Segment], settings: ExportSettings) -> List[str]:
        """
        Generates the FFmpeg command list based on segments and export settings.
        """
        if not self.ffmpeg_exec:
            raise FileNotFoundError("FFmpeg executable not found.")

        if not input_path or not os.path.exists(input_path):
             raise FileNotFoundError(f"Input file not found: {input_path}")

        if not segments:
             raise ValueError("No segments provided for export.")

        cmd = [self.ffmpeg_exec, "-y"]

        # --- INPUTS ---
        # Input 0: Main Video
        cmd.extend(["-i", input_path])
        
        # Input 1: Append Video (if exists)
        if settings.append_video_path:
            cmd.extend(["-i", settings.append_video_path])
        
        # Input 2 (or 1): External Audio (if exists)
        if settings.use_external_audio and settings.external_audio_path:
            cmd.extend(["-i", settings.external_audio_path])

        # Determine Input Indices
        # Main Video is always 0
        idx_main = 0
        idx_append = 1 if settings.append_video_path else None
        
        # External audio index depends on whether append video exists
        idx_ext_audio = None
        if settings.use_external_audio and settings.external_audio_path:
            idx_ext_audio = 2 if settings.append_video_path else 1

        # --- FILTER COMPLEX ---
        filter_parts = []
        
        # 1. Prepare MAIN Video (Input 0)
        # Collect segments
        concat_v_main_parts = []
        concat_a_main_parts = []
        
        for i, segment in enumerate(segments):
            start_sec = segment.start_ms / 1000.0
            end_sec = segment.end_ms / 1000.0
            
            # Video trim
            filter_parts.append(f"[0:v]trim=start={start_sec}:end={end_sec},setpts=PTS-STARTPTS[v_main_{i}]")
            concat_v_main_parts.append(f"[v_main_{i}]")
            
            # Audio trim (only if using original audio)
            if not settings.use_external_audio:
                filter_parts.append(f"[0:a]atrim=start={start_sec}:end={end_sec},asetpts=PTS-STARTPTS[a_main_{i}]")
                concat_a_main_parts.append(f"[a_main_{i}]")

        # Concat Main Segments
        n_segs = len(segments)
        
        # Main Video Concat
        v_main_cut_label = "[v_main_cut]"
        filter_parts.append(f"{''.join(concat_v_main_parts)}concat=n={n_segs}:v=1:a=0{v_main_cut_label}")
        
        # Main Audio Concat (if needed)
        a_main_cut_label = "[a_main_cut]"
        if not settings.use_external_audio:
            filter_parts.append(f"{''.join(concat_a_main_parts)}concat=n={n_segs}:v=0:a=1{a_main_cut_label}")

        # 2. Prepare APPEND Video (Input 1, if exists)
        v_app_label = "[v_app]"
        
        if idx_append is not None:
            # Scale append video to 4K to match main (assuming main is 4K or target is 4K)
            # Using 3840:2160 as requested
            filter_parts.append(f"[{idx_append}:v]scale=3840:2160,setsar=1[v_app_scaled]")
            v_app_label = "[v_app_scaled]" 

        # 3. FINAL CONCAT
        
        # --- VIDEO BRANCH ---
        if idx_append is not None:
            # Concat Main + Append
            filter_parts.append(f"{v_main_cut_label}{v_app_label}concat=n=2:v=1:a=0[outv]")
            map_v = "[outv]"
        else:
            # Just Main
            map_v = v_main_cut_label

        # --- AUDIO BRANCH ---
        map_a = ""
        
        # Scenario A: External Audio
        if settings.use_external_audio and settings.external_audio_path:
            # Ignore main audio cuts and append audio
            # Map directly from input
            map_a = f"{idx_ext_audio}:a"
            cmd.append("-shortest") # Cut audio to video length
            
        # Scenario B: Original Audio (No External)
        else:
            if idx_append is not None:
                # Concat Main Audio + Append Audio
                # Main audio is at a_main_cut_label
                # Append audio is at [{idx_append}:a]
                filter_parts.append(f"{a_main_cut_label}[{idx_append}:a]concat=n=2:v=0:a=1[outa]")
                map_a = "[outa]"
            else:
                # Just Main Audio
                map_a = a_main_cut_label

        # Assemble Filter Complex
        cmd.extend(["-filter_complex", ";".join(filter_parts)])
        
        # MAPPING
        cmd.extend(["-map", map_v])
        cmd.extend(["-map", map_a])
        
        # Determine output format and codecs
        ext = os.path.splitext(settings.output_path)[1].lower()
        if not ext:
             # Fallback if extension is missing in output_path but provided in settings.format
             # ideally settings.output_path should have it.
             ext = f".{settings.format}"

        mbps = settings.bitrate_mbps
        
        v_codec = 'libvpx-vp9'
        a_codec = 'libopus'
        # Default flags, will be overridden
        extra_flags = []

        if ext == '.mkv':
            # Use VP9 for MKV
            v_codec = 'libvpx-vp9'
            a_codec = 'libopus'
            # Constrained quality with target bitrate
            extra_flags = ['-b:v', f'{mbps}M', 
                           '-maxrate', f'{mbps + 5}M', 
                           '-bufsize', f'{mbps * 2}M', 
                           '-crf', '30', 
                           '-deadline', 'realtime', 
                           '-cpu-used', '4']
        elif ext == '.mp4':
            v_codec = 'libx264'
            a_codec = 'aac'
            extra_flags = ['-b:v', f'{mbps}M', 
                           '-maxrate', f'{mbps + 5}M', 
                           '-bufsize', f'{mbps * 2}M', 
                           '-preset', 'medium', 
                           '-pix_fmt', 'yuv420p']
        elif ext == '.webm':
             # Similar to MKV but WebM container
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
        
        cmd.append(settings.output_path)

        return cmd
