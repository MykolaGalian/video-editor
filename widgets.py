import sys
import subprocess
from typing import List
from PyQt6.QtWidgets import (QSlider, QDialog, QVBoxLayout, QTextBrowser, QPushButton, 
                             QStyle, QStyleOptionSlider)
from PyQt6.QtCore import Qt, QRect, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor

from models import Segment

class HelpDialog(QDialog):
    """Dialog to show user guide."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help - User Guide")
        self.resize(600, 500)
        
        layout = QVBoxLayout(self)
        
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setHtml("""
            <h2>User Guide for 4K Video Editor</h2>

            <h3>0. Requirements (Требования):</h3>
            <ul>
                <li>Для работы программы необходимы файлы <b>ffmpeg.exe</b> и <b>ffprobe.exe</b>.</li>
                <li>Положите их в папку с программой или укажите путь при экспорте.</li>
                <li>Без них экспорт и подсчет длительности не будут работать.</li>
            </ul>
            
            <h3>1. Loading & Trimming (Нарезка):</h3>
            <ul>
                <li>Загрузите основное видео ("Load Video").</li>
                <li>Используйте слайдер и кнопки "Set Start" / "Set End", чтобы выбрать ненужный фрагмент.</li>
                <li>Нажмите "Apply Cut", чтобы удалить выбранное. Это создаст "дырку" в видео.</li>
                <li>Плеер будет автоматически перепрыгивать удаленные участки при просмотре.</li>
            </ul>
            
            <h3>2. Appending (Склейка):</h3>
            <ul>
                <li>Используйте секцию "Append Video", чтобы добавить другой файл в КОНЕЦ основного видео.</li>
                <li>Прикрепленный файл добавится целиком (без нарезки).</li>
            </ul>
            
            <h3>3. Audio (Звук):</h3>
            <ul>
                <li>По умолчанию используется звук из видео.</li>
                <li>Можно загрузить внешний файл ("Load External Audio").</li>
                <li>Внешний звук заменит оригинальную дорожку и будет играть поверх всего видео.</li>
            </ul>
            
            <h3>4. Export (Сохранение):</h3>
            <ul>
                <li>Выберите формат (WebM, MKV, MP4).</li>
                <li>Настройте Битрейт слайдером (25-40 Mbps рекомендовано для 4K).</li>
                <li>Нажмите "Export Video". Процесс может занять время.</li>
            </ul>
        """)
        layout.addWidget(self.text_browser)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)


class TimelineSlider(QSlider):
    """Custom slider to visualize video segments and selection."""
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.start_val = 0
        self.end_val = 0
        self.segments: List[Segment] = []

    def set_selection(self, start: int, end: int):
        self.start_val = start
        self.end_val = end
        self.update()

    def set_segments(self, segments: List[Segment]):
        self.segments = segments
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        # 1. Draw Groove (Background)
        opt.subControls = QStyle.SubControl.SC_SliderGroove
        self.style().drawComplexControl(QStyle.ComplexControl.CC_Slider, opt, painter, self)

        # 2. Draw Segments (Green) and Selection (Blue)
        if self.maximum() > 0:
            groove_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
            total_range = self.maximum() - self.minimum()
            
            if total_range > 0:
                def val_to_x(val):
                    percent = (val - self.minimum()) / total_range
                    return int(groove_rect.left() + percent * groove_rect.width())

                # Draw Segments
                painter.setBrush(QColor(0, 200, 0))  # Green for kept segments
                painter.setPen(Qt.PenStyle.NoPen)
                for segment in self.segments:
                    x1 = val_to_x(segment.start_ms)
                    x2 = val_to_x(segment.end_ms)
                    # Ensure width is at least 1px if segment exists
                    w = max(1, x2 - x1)
                    rect = QRect(x1, groove_rect.top(), w, groove_rect.height())
                    painter.drawRect(rect)

                # Draw Selection (Blue, semi-transparent)
                if self.end_val > self.start_val:
                    x1 = val_to_x(self.start_val)
                    x2 = val_to_x(self.end_val)
                    selection_rect = QRect(x1, groove_rect.top(), x2 - x1, groove_rect.height())
                    painter.fillRect(selection_rect, QColor(0, 0, 200, 100))

        # 3. Draw Handle
        opt.subControls = QStyle.SubControl.SC_SliderHandle
        self.style().drawComplexControl(QStyle.ComplexControl.CC_Slider, opt, painter, self)

        # 4. Draw Playhead
        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        painter.setPen(QColor(255, 255, 255))
        center_x = handle_rect.center().x()
        painter.drawLine(center_x, handle_rect.top(), center_x, handle_rect.bottom())


class ExportThread(QThread):
    """Thread to run FFmpeg export command."""
    export_finished = pyqtSignal()
    error = pyqtSignal(str)
    progress_log = pyqtSignal(str)

    def __init__(self, command: List[str]):
        super().__init__()
        self.command = command
        self.process = None

    def run(self):
        try:
            # Hide console window on Windows
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                startupinfo=startupinfo
            )
            
            # Wait for completion and read output
            stdout, stderr = self.process.communicate()
            
            if self.process.returncode != 0:
                self.error.emit(f"FFmpeg Error:\n{stderr}")
            else:
                self.export_finished.emit()
                
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        if self.process:
            self.process.kill()
            self.process = None
