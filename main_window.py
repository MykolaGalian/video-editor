import os
import subprocess
from typing import List, Optional
from PyQt6.QtWidgets import (QMainWindow, QPushButton, QLabel, QSlider, QVBoxLayout, 
                             QHBoxLayout, QWidget, QFileDialog, QStyle, QMessageBox, QProgressBar)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import Qt, QUrl

from models import Segment, ExportSettings
from video_engine import FFmpegCommandBuilder
from widgets import TimelineSlider, HelpDialog, ExportThread

class MainWindow(QMainWindow):
    """Main application window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Open 4K Editor")
        self.resize(800, 600)

        # Initialize Engine
        self.ffmpeg_builder = FFmpegCommandBuilder()

        # Data
        self.start_time_ms: int = 0
        self.end_time_ms: int = 0
        self.segments: List[Segment] = []
        self.external_audio_path: Optional[str] = None
        self.appended_video_path: Optional[str] = None
        self.cached_append_duration: int = 0
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

        self.append_label = QLabel("No append video selected")
        append_layout.addWidget(self.append_label)

        self.select_append_btn = QPushButton("Select Video to Append")
        self.select_append_btn.clicked.connect(self.select_append_video)
        append_layout.addWidget(self.select_append_btn)

        self.clear_append_btn = QPushButton("Clear")
        self.clear_append_btn.clicked.connect(self.clear_append_video)
        append_layout.addWidget(self.clear_append_btn)

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
        self.media_player.durationChanged.connect(self.duration_changed)

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
        main_len_ms = sum(seg.end_ms - seg.start_ms for seg in self.segments)
        
        append_len_ms = 0
        if self.appended_video_path:
            append_len_ms = self.cached_append_duration
            
        total_ms = main_len_ms + append_len_ms
        self.duration_label.setText(f"Total Duration: {self.format_time(total_ms)}")

    def show_help(self):
        dialog = HelpDialog(self)
        dialog.exec()

    def update_slider_selection(self):
        self.slider.set_selection(self.start_time_ms, self.end_time_ms)

    def open_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Video Files (*.mp4 *.webm *.mkv)")
        if file_name:
            self.path_label.setText(file_name)
            self.segments = [] # Clear segments from previous video
            self.media_player.setSource(QUrl.fromLocalFile(file_name))
            self.play_btn.setEnabled(True)
            self.play_video()
            # update_total_duration will be called in duration_changed

    def play_video(self):
        self.is_previewing = False
        self.media_player.play()

    def pause_video(self):
        self.media_player.pause()

    def stop_video(self):
        self.media_player.stop()

    def position_changed(self, position):
        if not self.slider.isSliderDown():
            self.slider.setValue(position)
        
        # Smart Player / Gap Jumping Logic
        in_segment = False
        for segment in self.segments:
            if segment.start_ms <= position < segment.end_ms:
                in_segment = True
                break
        
        if not in_segment and self.segments:
            # Find nearest NEXT segment
            next_seg_start = None
            for segment in self.segments:
                if segment.start_ms > position:
                    next_seg_start = segment.start_ms
                    break
            
            if next_seg_start is not None:
                self.media_player.setPosition(next_seg_start)
            else:
                if self.segments and position > self.segments[-1].end_ms:
                     self.media_player.pause()

    def duration_changed(self, duration):
        self.slider.setRange(0, duration)
        self.end_time_ms = duration
        if not self.segments:
            self.segments = [Segment(0, duration)]
            self.slider.set_segments(self.segments)
        self.end_label.setText(f"End: {self.format_time(duration)}")
        self.update_total_duration()

    def set_position(self, position):
        self.media_player.setPosition(position)

    def format_time(self, ms):
        seconds = (ms // 1000) % 60
        minutes = (ms // 60000) % 60
        hours = (ms // 3600000)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def set_start(self):
        self.start_time_ms = self.media_player.position()
        if self.start_time_ms > self.end_time_ms:
            self.end_time_ms = self.media_player.duration()
            self.end_label.setText(f"End: {self.format_time(self.end_time_ms)}")
        self.start_label.setText(f"Start: {self.format_time(self.start_time_ms)}")
        self.update_slider_selection()

    def set_end(self):
        self.end_time_ms = self.media_player.position()
        if self.end_time_ms < self.start_time_ms:
            self.start_time_ms = 0
            self.start_label.setText(f"Start: {self.format_time(self.start_time_ms)}")
        self.end_label.setText(f"End: {self.format_time(self.end_time_ms)}")
        self.update_slider_selection()

    def reset_trim(self):
        self.start_time_ms = 0
        self.end_time_ms = self.media_player.duration()
        self.start_label.setText(f"Start: {self.format_time(self.start_time_ms)}")
        self.end_label.setText(f"End: {self.format_time(self.end_time_ms)}")
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
        self.media_player.setPosition(self.start_time_ms)
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

    def select_append_video(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Video to Append", "", "Video Files (*.mp4 *.webm *.mkv)")
        if file_name:
            self.appended_video_path = file_name
            self.cached_append_duration = self.get_external_duration(file_name)
            self.append_label.setText(f"Append: {os.path.basename(file_name)}")
            self.update_total_duration()

    def clear_append_video(self):
        self.appended_video_path = None
        self.cached_append_duration = 0
        self.append_label.setText("No append video selected")
        self.update_total_duration()

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
            external_audio_path=self.external_audio_path,
            append_video_path=self.appended_video_path
        )

        try:
            command = self.ffmpeg_builder.build_command(
                input_path=self.path_label.text(),
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
        self.select_append_btn.setEnabled(enabled)
        self.clear_append_btn.setEnabled(enabled)
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
