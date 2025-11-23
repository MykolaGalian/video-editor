import os
import subprocess
from typing import List, Optional
import sys
from PyQt6.QtWidgets import (QMainWindow, QPushButton, QLabel, QSlider, QVBoxLayout, 
                             QHBoxLayout, QWidget, QFileDialog, QStyle, QMessageBox, 
                             QProgressBar, QComboBox, QGroupBox, QMenu)
from PyQt6.QtGui import QIcon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import Qt, QUrl

from models import Segment, ExportSettings, SourceClip
from video_engine import FFmpegCommandBuilder
from widgets import TimelineSlider, HelpDialog, ExportThread
from timeline_manager import TimelineManager

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class MainWindow(QMainWindow):
    """Main application window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Open 4K Editor")
        self.setWindowIcon(QIcon(resource_path("assets/icon.png")))
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
        """Initialize UI components with a structured layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # --- ZONE 1: VIDEO & TIMELINE (Top) ---
        video_group = QGroupBox()
        video_group.setStyleSheet("QGroupBox { border: 0px; }") # Minimalist
        video_layout = QVBoxLayout(video_group)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        # Path Label
        self.path_label = QLabel("No file selected")
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        video_layout.addWidget(self.path_label)

        # Video Widget
        self.video_widget = QVideoWidget()
        video_layout.addWidget(self.video_widget, 1)

        # Timeline Row
        timeline_layout = QHBoxLayout()
        
        self.start_label = QLabel("00:00:00")
        timeline_layout.addWidget(self.start_label)

        self.slider = TimelineSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.set_position)
        timeline_layout.addWidget(self.slider, 1)

        self.end_label = QLabel("00:00:00")
        timeline_layout.addWidget(self.end_label)
        
        video_layout.addLayout(timeline_layout)
        
        main_layout.addWidget(video_group, 1) # Expandable

        # --- ZONE 2: TOOLBAR (Bottom, Fixed Height) ---
        tools_group = QGroupBox()
        tools_group.setFixedHeight(180) 
        tools_layout = QHBoxLayout(tools_group)
        
        # SECTION A: EDITING TOOLS (Left)
        edit_layout = QVBoxLayout()
        edit_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        edit_label = QLabel("<b>Edit</b>")
        edit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit_layout.addWidget(edit_label)
        
        # Edit Buttons Row 1
        edit_btns_1 = QHBoxLayout()
        self.set_start_btn = QPushButton("[ In")
        self.set_start_btn.setToolTip("Set Start Point")
        self.set_start_btn.clicked.connect(self.set_start)
        edit_btns_1.addWidget(self.set_start_btn)
        
        self.set_end_btn = QPushButton("Out ]")
        self.set_end_btn.setToolTip("Set End Point")
        self.set_end_btn.clicked.connect(self.set_end)
        edit_btns_1.addWidget(self.set_end_btn)
        edit_layout.addLayout(edit_btns_1)
        
        # Edit Buttons Row 2
        edit_btns_2 = QHBoxLayout()
        self.apply_cut_btn = QPushButton("✂ Cut")
        self.apply_cut_btn.setToolTip("Remove Selected Area")
        self.apply_cut_btn.setStyleSheet("background-color: #c62828; color: white; font-weight: bold;") 
        self.apply_cut_btn.clicked.connect(self.apply_cut)
        edit_btns_2.addWidget(self.apply_cut_btn)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.reset_trim)
        edit_btns_2.addWidget(self.reset_btn)
        edit_layout.addLayout(edit_btns_2)

        # Preview Cut (Hidden/Optional or Small)
        self.preview_btn = QPushButton("Preview Cut")
        self.preview_btn.clicked.connect(self.preview_cut)
        edit_layout.addWidget(self.preview_btn)
        
        tools_layout.addLayout(edit_layout)
        tools_layout.addStretch() # Separator
        
        # SECTION B: TRANSPORT & CONTENT (Center)
        transport_layout = QVBoxLayout()
        transport_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        transport_label = QLabel("<b>Playback & Clips</b>")
        transport_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        transport_layout.addWidget(transport_label)
        
        # Player Controls
        player_controls = QHBoxLayout()
        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_btn.clicked.connect(self.stop_video)
        player_controls.addWidget(self.stop_btn)
        
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_btn.clicked.connect(self.play_video)
        player_controls.addWidget(self.play_btn)
        
        self.pause_btn = QPushButton()
        self.pause_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.pause_btn.clicked.connect(self.pause_video)
        player_controls.addWidget(self.pause_btn)
        transport_layout.addLayout(player_controls)
        
        # Content Controls
        content_controls = QHBoxLayout()
        
        self.add_clip_btn = QPushButton("Add Clip (+)")
        self.add_clip_btn.clicked.connect(self.add_clip)
        content_controls.addWidget(self.add_clip_btn)
        
        self.clear_timeline_btn = QPushButton("Clear")
        self.clear_timeline_btn.clicked.connect(self.clear_timeline)
        content_controls.addWidget(self.clear_timeline_btn)
        
        # Audio Button with Menu
        self.load_audio_btn = QPushButton("Music ▾")
        self.load_audio_menu = QMenu()
        self.load_audio_action = self.load_audio_menu.addAction("Load External Audio")
        self.load_audio_action.triggered.connect(self.load_external_audio)
        self.clear_audio_action = self.load_audio_menu.addAction("Clear Audio")
        self.clear_audio_action.triggered.connect(self.clear_external_audio)
        self.load_audio_btn.setMenu(self.load_audio_menu)
        content_controls.addWidget(self.load_audio_btn)
        
        transport_layout.addLayout(content_controls)

        # Keep references to old buttons to avoid errors if referenced elsewhere, 
        # though we should check usages. 
        # self.load_btn was "New Project". I'll alias it to add_clip or just keep it hidden/removed?
        # Let's keep it as a hidden member if needed, or just remove it. 
        # Wait, open_file is useful for "New Project". 
        # I'll add a small "New" button or just rely on Add Clip?
        # "Add Clip" adds to timeline. "Open File" clears and adds.
        # I'll add a "New" button to content controls.
        self.load_btn = QPushButton("New")
        self.load_btn.clicked.connect(self.open_file)
        content_controls.insertWidget(0, self.load_btn)

        # Audio status label - maybe put it in transport layout?
        self.audio_status_label = QLabel("Audio: Original")
        self.audio_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        transport_layout.addWidget(self.audio_status_label)

        # Help button
        self.help_btn = QPushButton("?")
        self.help_btn.setFixedWidth(30)
        self.help_btn.clicked.connect(self.show_help)
        # Add to top right of transport or somewhere?
        # Let's add it to the edit layout top right?
        # Or just append to transport layout
        
        tools_layout.addLayout(transport_layout)
        tools_layout.addStretch()
        
        # SECTION C: EXPORT (Right)
        export_layout = QVBoxLayout()
        export_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        export_label = QLabel("<b>Export</b>")
        export_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        export_layout.addWidget(export_label)
        
        # Bitrate
        self.bitrate_label = QLabel("Bitrate: 25 Mbps")
        export_layout.addWidget(self.bitrate_label)
        self.bitrate_slider = QSlider(Qt.Orientation.Horizontal)
        self.bitrate_slider.setRange(5, 60)
        self.bitrate_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.bitrate_slider.setTickInterval(5)
        self.bitrate_slider.setValue(25)
        self.bitrate_slider.valueChanged.connect(self.update_bitrate_label)
        export_layout.addWidget(self.bitrate_slider)
        
        # FPS
        fps_row = QHBoxLayout()
        self.fps_label = QLabel("FPS:")
        fps_row.addWidget(self.fps_label)
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["59.94", "50", "29.97", "25", "23.976"])
        self.fps_combo.setCurrentText("23.976")
        fps_row.addWidget(self.fps_combo)
        export_layout.addLayout(fps_row)
        
        # Duration Label (Effective)
        self.duration_label = QLabel("Total: 00:00:00")
        export_layout.addWidget(self.duration_label)

        # Export Button
        self.export_btn = QPushButton("EXPORT")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; 
                color: white; 
                font-weight: bold; 
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #aaaaaa;
            }
        """)
        self.export_btn.clicked.connect(self.start_export)
        export_layout.addWidget(self.export_btn)
        
        # Export Status Label
        self.export_status_label = QLabel("Exporting...")
        self.export_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.export_status_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        self.export_status_label.setVisible(False)
        export_layout.addWidget(self.export_status_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        export_layout.addWidget(self.progress_bar)
        
        tools_layout.addLayout(export_layout)
        
        main_layout.addWidget(tools_group)
        
        # Add Help button to the very bottom right or top right?
        # Let's put it in the main layout top right?
        # Or just add it to the tools group?
        # I'll add it to the Edit layout for now, or maybe just float it?
        # I'll add it to the Edit layout.
        edit_layout.addWidget(self.help_btn)

        # Unused buttons from old UI that need to be defined to avoid errors if referenced:
        self.clear_audio_btn = QPushButton() # Dummy, action moved to menu

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
        # Slider range is based on the full timeline (including gaps)
        timeline_len_ms = self.timeline_manager.get_total_duration()
        self.slider.setRange(0, timeline_len_ms)
        self.end_label.setText(f"End: {self.format_time(timeline_len_ms)}")

        # Effective duration is the sum of all "Keep" segments
        effective_ms = sum(seg.end_ms - seg.start_ms for seg in self.segments)
        self.duration_label.setText(f"Final Duration: {self.format_time(effective_ms)}")

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
            external_audio_path=self.external_audio_path,
            fps=float(self.fps_combo.currentText())
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
        self.export_btn.setVisible(False)
        self.export_status_label.setVisible(True)
        self.progress_bar.setVisible(True)
        self.path_label.setText("Exporting... Please wait.")

    def on_export_finished(self):
        self.set_controls_enabled(True)
        self.export_btn.setVisible(True)
        self.export_status_label.setVisible(False)
        self.progress_bar.setVisible(False)
        self.path_label.setText(self.media_player.source().toLocalFile())
        QMessageBox.information(self, "Success", "Export completed successfully!")
        self.export_thread = None

    def on_export_error(self, error_msg):
        self.set_controls_enabled(True)
        self.export_btn.setVisible(True)
        self.export_status_label.setVisible(False)
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
