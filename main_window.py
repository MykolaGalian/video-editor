import os
import subprocess
from typing import List, Optional
from PyQt6.QtWidgets import (QMainWindow, QPushButton, QLabel, QSlider, QVBoxLayout, 
                             QHBoxLayout, QWidget, QFileDialog, QStyle, QMessageBox, QProgressBar)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import Qt, QUrl

from models import Segment, ExportSettings, SourceClip
from video_engine import FFmpegCommandBuilder
from widgets import TimelineSlider, HelpDialog, ExportThread
from timeline_manager import TimelineManager

class MainWindow(QMainWindow):
    """Main application window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Open 4K Editor")
        self.resize(800, 600)

        # Initialize Engine
        self.ffmpeg_builder = FFmpegCommandBuilder()

        # Data
        self.timeline_manager = TimelineManager()
        self.current_clip: Optional[SourceClip] = None
        
        self.start_time_ms: int = 0
        self.end_time_ms: int = 0
        self.segments: List[Segment] = []
        self.external_audio_path: Optional[str] = None
        self.export_thread: Optional[ExportThread] = None
        self.is_previewing: bool = False

        # UI Setup
        self._init_ui()
        self._init_media_player()
        self._check_ffmpeg()

    def _init_ui(self):
        """Initialize UI components."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Video Widget
        self.video_widget = QVideoWidget()
        layout.addWidget(self.video_widget, 1)

        # File Path Label
        self.path_label = QLabel("No file selected")
        layout.addWidget(self.path_label)

        # Slider (Timeline)
        self.slider = TimelineSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.set_position)
        layout.addWidget(self.slider)

        # Control Buttons Layout
        controls_layout = QHBoxLayout()
        layout.addLayout(controls_layout)

        # Load Button
        self.load_btn = QPushButton("Загрузить видео")
        self.load_btn.clicked.connect(self.open_file)
        controls_layout.addWidget(self.load_btn)

        # Help Button
        self.help_btn = QPushButton("?")
        self.help_btn.setFixedWidth(50)
        self.help_btn.clicked.connect(self.show_help)
        controls_layout.addWidget(self.help_btn)

        # Play Button
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_btn.clicked.connect(self.play_video)
        controls_layout.addWidget(self.play_btn)

        # Pause Button
        self.pause_btn = QPushButton()
        self.pause_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.pause_btn.clicked.connect(self.pause_video)
        controls_layout.addWidget(self.pause_btn)

        # Stop Button
        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_btn.clicked.connect(self.stop_video)
        controls_layout.addWidget(self.stop_btn)

        # Trim Controls Layout
        trim_layout = QHBoxLayout()
        layout.addLayout(trim_layout)

        # Apply Cut Button
        self.apply_cut_btn = QPushButton("Apply Cut (Remove Selection)")
        self.apply_cut_btn.clicked.connect(self.apply_cut)
        trim_layout.addWidget(self.apply_cut_btn)

        # Start Time
        self.start_label = QLabel("Start: 00:00:00")
        trim_layout.addWidget(self.start_label)

        self.set_start_btn = QPushButton("[ Set Start ]")
        self.set_start_btn.clicked.connect(self.set_start)
        trim_layout.addWidget(self.set_start_btn)

        # End Time
        self.set_end_btn = QPushButton("[ Set End ]")
        self.set_end_btn.clicked.connect(self.set_end)
        trim_layout.addWidget(self.set_end_btn)

        self.end_label = QLabel("End: 00:00:00")
        trim_layout.addWidget(self.end_label)

        # Reset & Preview
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.reset_trim)
        trim_layout.addWidget(self.reset_btn)

        self.preview_btn = QPushButton("Preview Cut")
        self.preview_btn.clicked.connect(self.preview_cut)
        trim_layout.addWidget(self.preview_btn)

        # Audio Controls Layout
        audio_layout = QHBoxLayout()
        layout.addLayout(audio_layout)

        # Load External Audio Button
        self.load_audio_btn = QPushButton("Load External Audio")
        self.load_audio_btn.clicked.connect(self.load_external_audio)
        audio_layout.addWidget(self.load_audio_btn)

        # Clear Audio Button
        self.clear_audio_btn = QPushButton("Clear Audio")
        self.clear_audio_btn.clicked.connect(self.clear_external_audio)
        audio_layout.addWidget(self.clear_audio_btn)

        # Audio Status Label
        self.audio_status_label = QLabel("Audio: Original")
        audio_layout.addWidget(self.audio_status_label)

        # Append Video Controls Layout
        append_layout = QHBoxLayout()
        layout.addLayout(append_layout)

        self.add_clip_btn = QPushButton("Add Clip to Timeline")
        self.add_clip_btn.clicked.connect(self.add_clip)
        append_layout.addWidget(self.add_clip_btn)
        
        self.clear_timeline_btn = QPushButton("Clear Timeline")
        self.clear_timeline_btn.clicked.connect(self.clear_timeline)
        append_layout.addWidget(self.clear_timeline_btn)

        # Export Controls Layout
        export_layout = QHBoxLayout()
        layout.addLayout(export_layout)

        # Bitrate Settings
        bitrate_layout = QVBoxLayout()
        export_layout.addLayout(bitrate_layout)

        self.bitrate_label = QLabel("Bitrate: 25 Mbps")
        bitrate_layout.addWidget(self.bitrate_label)

        self.bitrate_slider = QSlider(Qt.Orientation.Horizontal)
        self.bitrate_slider.setRange(5, 60)
        self.bitrate_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.bitrate_slider.setTickInterval(5)
        self.bitrate_slider.valueChanged.connect(self.update_bitrate_label)
        self.bitrate_slider.setValue(25) 
        bitrate_layout.addWidget(self.bitrate_slider)

        # Total Duration Label
        self.duration_label = QLabel("Total Duration: 00:00:00")
        self.duration_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        export_layout.addWidget(self.duration_label)

        # Export Button
        self.export_btn = QPushButton("Export Video")
        self.export_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
        self.export_btn.clicked.connect(self.start_export)
        export_layout.addWidget(self.export_btn)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminate
        self.progress_bar.setVisible(False)
        export_layout.addWidget(self.progress_bar)

    def _init_media_player(self):
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.mediaStatusChanged.connect(self.media_status_changed)
        # self.media_player.durationChanged.connect(self.duration_changed) # We handle duration manually now

    def _check_ffmpeg(self):
        if not self.ffmpeg_builder.get_ffmpeg_path():
            # Try to find it again or warn user?
            # For now just leave it None, will prompt on export
            pass

    def get_external_duration(self, file_path: str) -> int:
        try:
            ffmpeg_path = self.ffmpeg_builder.get_ffmpeg_path()
            if not ffmpeg_path:
                return 0
            
            ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe.exe")
            if not os.path.exists(ffprobe_path):
                return 0
                
            cmd = [
                ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration_sec = float(result.stdout.strip())
            return int(duration_sec * 1000)
        except Exception:
            return 0

    def update_total_duration(self):
        total_ms = self.timeline_manager.get_total_duration()
        self.duration_label.setText(f"Total Duration: {self.format_time(total_ms)}")
        self.slider.setRange(0, total_ms)
        self.end_label.setText(f"End: {self.format_time(total_ms)}")

    def show_help(self):
        dialog = HelpDialog(self)
        dialog.exec()

    def update_slider_selection(self):
        self.slider.set_selection(self.start_time_ms, self.end_time_ms)

    def open_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Video Files (*.mp4 *.webm *.mkv)")
        if file_name:
            # New Project behavior
            self.timeline_manager.clear()
            self.segments = []
            
            duration = self.get_external_duration(file_name)
            if duration == 0:
                QMessageBox.warning(self, "Error", "Could not determine video duration.")
                return

            self.timeline_manager.add_clip(file_name, duration)
            self.current_clip = self.timeline_manager.playlist[0]
            
            self.path_label.setText(f"Playlist: 1 clip ({os.path.basename(file_name)})")
            
            # Initialize segments with global duration
            self.segments = [Segment(0, duration)]
            self.slider.set_segments(self.segments)
            
            self.media_player.setSource(QUrl.fromLocalFile(file_name))
            self.play_btn.setEnabled(True)
            self.play_video()
            self.update_total_duration()

    def add_clip(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Add Clip", "", "Video Files (*.mp4 *.webm *.mkv)")
        if file_name:
            duration = self.get_external_duration(file_name)
            if duration == 0:
                QMessageBox.warning(self, "Error", "Could not determine video duration.")
                return
                
            self.timeline_manager.add_clip(file_name, duration)
            
            # Update segments - add new segment for the new clip
            # Actually, segments are "Keep" zones. If we add a clip, we probably want to keep it by default.
            new_clip = self.timeline_manager.playlist[-1]
            self.segments.append(Segment(new_clip.global_start_ms, new_clip.global_end_ms))
            self.segments.sort(key=lambda x: x.start_ms)
            self.slider.set_segments(self.segments)
            
            self.path_label.setText(f"Playlist: {len(self.timeline_manager.playlist)} clips")
            self.update_total_duration()

    def clear_timeline(self):
        self.timeline_manager.clear()
        self.segments = []
        self.slider.set_segments([])
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.path_label.setText("No file selected")
        self.update_total_duration()

    def play_video(self):
        self.is_previewing = False
        self.media_player.play()

    def pause_video(self):
        self.media_player.pause()

    def stop_video(self):
        self.media_player.stop()

    def position_changed(self, position):
        if not self.current_clip:
            return

        # Calculate global position
        global_pos = self.current_clip.global_start_ms + position
        
        if not self.slider.isSliderDown():
            self.slider.setValue(global_pos)
        
        # Smart Player / Gap Jumping Logic (Global Time)
        in_segment = False
        for segment in self.segments:
            if segment.start_ms <= global_pos < segment.end_ms:
                in_segment = True
                break
        
        if not in_segment and self.segments:
            # Find nearest NEXT segment
            next_seg_start = None
            for segment in self.segments:
                if segment.start_ms > global_pos:
                    next_seg_start = segment.start_ms
                    break
            
            if next_seg_start is not None:
                self.set_position(next_seg_start)
            else:
                if self.segments and global_pos > self.segments[-1].end_ms:
                     self.media_player.pause()

    def media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            next_clip = self.timeline_manager.get_next_clip(self.current_clip)
            if next_clip:
                self.current_clip = next_clip
                self.media_player.setSource(QUrl.fromLocalFile(next_clip.path))
                self.media_player.play()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            QMessageBox.critical(self, "Playback Error", 
                                 f"Could not play video: {self.current_clip.path if self.current_clip else 'Unknown'}\n"
                                 "The file might be corrupted or the format is not supported.")

    def duration_changed(self, duration):
        # We handle duration manually via timeline_manager
        pass

    def set_position(self, position):
        """Seek to global position."""
        clip, local_ms = self.timeline_manager.get_clip_at_global_time(position)
        
        if not clip:
            return

        if clip != self.current_clip:
            self.current_clip = clip
            self.media_player.setSource(QUrl.fromLocalFile(clip.path))
            # If we were playing, keep playing. If paused, stay paused?
            # For simplicity, let's play if we are dragging slider or jumping gaps
            self.media_player.play() 
        
        self.media_player.setPosition(local_ms)

    def format_time(self, ms):
        seconds = (ms // 1000) % 60
        minutes = (ms // 60000) % 60
        hours = (ms // 3600000)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def set_start(self):
        # Use slider value which is Global Time
        self.start_time_ms = self.slider.value()
        if self.start_time_ms > self.end_time_ms:
            self.end_time_ms = self.timeline_manager.get_total_duration()
            self.end_label.setText(f"End: {self.format_time(self.end_time_ms)}")
        self.start_label.setText(f"Start: {self.format_time(self.start_time_ms)}")
        self.update_slider_selection()

    def set_end(self):
        self.end_time_ms = self.slider.value()
        if self.end_time_ms < self.start_time_ms:
            self.start_time_ms = 0
            self.start_label.setText(f"Start: {self.format_time(self.start_time_ms)}")
        self.end_label.setText(f"End: {self.format_time(self.end_time_ms)}")
        self.update_slider_selection()

    def reset_trim(self):
        self.start_time_ms = 0
        self.end_time_ms = self.timeline_manager.get_total_duration()
        self.start_label.setText(f"Start: {self.format_time(self.start_time_ms)}")
        self.end_label.setText(f"End: {self.format_time(self.end_time_ms)}")
        self.update_slider_selection()
        self.update_total_duration()

    def apply_cut(self):
        sel_start = self.start_time_ms
        sel_end = self.end_time_ms
        
        if sel_start >= sel_end:
            return

        new_segments = []
        for segment in self.segments:
            seg_start = segment.start_ms
            seg_end = segment.end_ms

            # Case 1: Selection completely covers segment -> Remove segment
            if sel_start <= seg_start and sel_end >= seg_end:
                continue
            
            # Case 2: No overlap -> Keep segment
            elif sel_end <= seg_start or sel_start >= seg_end:
                new_segments.append(segment)
            
            # Case 3: Partial overlap
            else:
                # If selection cuts the beginning
                if sel_start <= seg_start < sel_end:
                    new_segments.append(Segment(sel_end, seg_end))
                # If selection cuts the end
                elif sel_start < seg_end <= sel_end:
                    new_segments.append(Segment(seg_start, sel_start))
                # If selection is in the middle
                elif seg_start < sel_start and sel_end < seg_end:
                    new_segments.append(Segment(seg_start, sel_start))
                    new_segments.append(Segment(sel_end, seg_end))
        
        new_segments.sort(key=lambda x: x.start_ms)
        self.segments = new_segments
        self.slider.set_segments(self.segments)
        
        self.start_time_ms = 0
        self.end_time_ms = 0
        self.update_slider_selection()
        self.start_label.setText(f"Start: {self.format_time(0)}")
        self.start_label.setText(f"Start: {self.format_time(0)}")
        self.end_label.setText(f"End: {self.format_time(0)}")
        self.update_total_duration()

    def preview_cut(self):
        self.set_position(self.start_time_ms)
        self.media_player.play()

    def load_external_audio(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Audio", "", "Audio Files (*.mp3 *.wav *.aac)")
        if file_name:
            self.external_audio_path = file_name
            self.audio_status_label.setText(f"Audio: {os.path.basename(file_name)}")
            QMessageBox.information(self, "Audio Loaded", 
                                    "External audio will be applied during Export only.\n"
                                    "Preview plays original audio.")

    def clear_external_audio(self):
        self.external_audio_path = None
        self.audio_status_label.setText("Audio: Original")

    # Append methods removed

    def update_bitrate_label(self, value):
        step = 5
        snapped_value = round(value / step) * step

        if value != snapped_value:
            self.bitrate_slider.blockSignals(True)
            self.bitrate_slider.setValue(snapped_value)
            self.bitrate_slider.blockSignals(False)
            value = snapped_value

        self.bitrate_label.setText(f"Bitrate: {value} Mbps")

    def start_export(self):
        if self.path_label.text() == "No file selected":
            QMessageBox.warning(self, "Error", "No video loaded.")
            return

        # Check for FFmpeg
        if not self.ffmpeg_builder.get_ffmpeg_path():
            QMessageBox.warning(self, "FFmpeg not found", "FFmpeg not found. Please specify the path to ffmpeg.exe")
            ffmpeg_path, _ = QFileDialog.getOpenFileName(self, "Select FFmpeg Executable", "", "Executables (*.exe)")
            if ffmpeg_path:
                self.ffmpeg_builder.set_ffmpeg_path(ffmpeg_path)
            else:
                return

        output_path, _ = QFileDialog.getSaveFileName(self, "Export Video", "", "WebM Video (*.webm);;MKV Video (*.mkv);;MP4 Video (*.mp4)")
        if not output_path:
            return

        # Create ExportSettings
        settings = ExportSettings(
            output_path=output_path,
            format=os.path.splitext(output_path)[1][1:], # Remove dot
            bitrate_mbps=self.bitrate_slider.value(),
            use_external_audio=bool(self.external_audio_path),
            external_audio_path=self.external_audio_path
        )

        try:
            command = self.ffmpeg_builder.build_command(
                playlist=self.timeline_manager.playlist,
                segments=self.segments,
                settings=settings
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        self.export_thread = ExportThread(command)
        self.export_thread.started.connect(self.on_export_started)
        self.export_thread.export_finished.connect(self.on_export_finished)
        self.export_thread.error.connect(self.on_export_error)
        self.export_thread.start()

    def on_export_started(self):
        self.set_controls_enabled(False)
        self.progress_bar.setVisible(True)
        self.path_label.setText("Exporting... Please wait.")

    def on_export_finished(self):
        self.set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        self.path_label.setText(self.media_player.source().toLocalFile())
        QMessageBox.information(self, "Success", "Export completed successfully!")
        self.export_thread = None

    def on_export_error(self, error_msg):
        self.set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        self.path_label.setText(self.media_player.source().toLocalFile())
        QMessageBox.critical(self, "Export Error", error_msg)
        self.export_thread = None

    def set_controls_enabled(self, enabled):
        self.load_btn.setEnabled(enabled)
        self.play_btn.setEnabled(enabled)
        self.pause_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(enabled)
        self.apply_cut_btn.setEnabled(enabled)
        self.set_start_btn.setEnabled(enabled)
        self.set_end_btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)
        self.preview_btn.setEnabled(enabled)
        self.load_audio_btn.setEnabled(enabled)
        self.clear_audio_btn.setEnabled(enabled)
        self.add_clip_btn.setEnabled(enabled)
        self.clear_timeline_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)

    def closeEvent(self, event):
        if self.export_thread and self.export_thread.isRunning():
            reply = QMessageBox.question(self, 'Exit', 
                                         'Export is in progress. Are you sure you want to quit? The process will be terminated.',
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.export_thread.stop()
                self.export_thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
