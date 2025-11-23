import sys
import subprocess
from typing import List
from PyQt6.QtWidgets import (QSlider, QDialog, QVBoxLayout, QTextBrowser, QPushButton, 
                             QStyle, QStyleOptionSlider)
from PyQt6.QtCore import Qt, QRect, QThread, pyqtSignal, QSize
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
            </ul>
            
            <h3>1. Virtual Global Timeline (Виртуальный Таймлайн):</h3>
            <ul>
                <li><b>New</b>: Начинает новый проект (очищает таймлайн).</li>
                <li><b>Add Clip (+)</b>: Добавляет видео в конец текущего таймлайна.</li>
                <li>Программа воспринимает все добавленные файлы как одну длинную "ленту".</li>
                <li>Вы можете резать и удалять куски в любом месте, даже на стыке файлов.</li>
            </ul>

            <h3>2. Trimming (Нарезка):</h3>
            <ul>
                <li>Используйте слайдер и кнопки <b>[ In</b> / <b>Out ]</b>, чтобы выбрать фрагмент.</li>
                <li><b>✂ Cut</b>: Удаляет выбранный участок из таймлайна.</li>
                <li>Плеер автоматически пропускает удаленные участки ("дырки").</li>
                <li>Кнопка <b>Reset</b> сбрасывает выделение, но НЕ отменяет сделанные вырезы.</li>
                <li>Чтобы начать заново, используйте <b>Clear</b> или <b>New</b>.</li>
            </ul>
            
            <h3>3. Audio (Звук):</h3>
            <ul>
                <li>По умолчанию используется оригинальный звук из видеофайлов.</li>
                <li>Меню <b>Music ▾</b>: Позволяет загрузить или очистить внешний аудиофайл.</li>
                <li><b>Load External Audio</b>: Заменяет звук во ВСЕМ проекте на внешний файл.</li>
                <li>Внешний звук будет обрезан или зациклен под длину видео.</li>
            </ul>
            
            <h3>4. Export (Сохранение):</h3>
            <ul>
                <li>Все клипы и вырезы склеиваются в один итоговый файл.</li>
                <li>Выберите формат (WebM, MKV, MP4) и битрейт.</li>
                <li>Нажмите "Export Video".</li>
            </ul>
        """)
        layout.addWidget(self.text_browser)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)


class TimelineSlider(QSlider):
    """Custom slider to visualize video segments, selection, and time scale."""
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.start_val = 0
        self.end_val = 0
        self.segments: List[Segment] = []

    def sizeHint(self):
        """Increase height to accommodate time labels."""
        s = super().sizeHint()
        return QSize(s.width(), s.height() + 30)

    def set_selection(self, start: int, end: int):
        self.start_val = start
        self.end_val = end
        self.update()

    def set_segments(self, segments: List[Segment]):
        self.segments = segments
        self.update()

    def format_time_short(self, ms: int) -> str:
        """Format time as MM:SS or H:MM:SS."""
        seconds = ms // 1000
        minutes = seconds // 60
        hours = minutes // 60
        
        seconds %= 60
        minutes %= 60
        
        if self.maximum() < 3600000: # Less than 1 hour
            return f"{minutes:02}:{seconds:02}"
        else:
            return f"{hours}:{minutes:02}:{seconds:02}"

    def paintEvent(self, event):
        painter = QPainter(self)
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        # 1. Draw Groove (Background)
        opt.subControls = QStyle.SubControl.SC_SliderGroove
        self.style().drawComplexControl(QStyle.ComplexControl.CC_Slider, opt, painter, self)
        
        groove_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        total_range = self.maximum() - self.minimum()

        # Helper to map value to x coordinate
        def val_to_x(val):
            if total_range <= 0: return groove_rect.left()
            percent = (val - self.minimum()) / total_range
            return int(groove_rect.left() + percent * groove_rect.width())

        # 2. Draw Segments (Green) and Selection (Blue)
        if self.maximum() > 0 and total_range > 0:
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

            # 3. Draw Time Scale (Ticks and Labels)
            min_pixel_spacing = 80
            widget_width = self.width()
            if widget_width > 0:
                min_ms_step = (total_range / widget_width) * min_pixel_spacing
                
                # Allowed steps: 1s, 5s, 10s, 30s, 1m, 5m, 10m, 30m, 1h
                allowed_steps = [
                    1000, 5000, 10000, 30000, 
                    60000, 300000, 600000, 1800000, 
                    3600000
                ]
                
                draw_step = allowed_steps[-1]
                for step in allowed_steps:
                    if step >= min_ms_step:
                        draw_step = step
                        break
                
                painter.setPen(Qt.GlobalColor.gray)
                font = painter.font()
                font.setPointSize(8)
                painter.setFont(font)
                
                # Start from the first multiple of draw_step
                start_t = (self.minimum() // draw_step) * draw_step
                if start_t < self.minimum():
                    start_t += draw_step
                    
                for t in range(start_t, self.maximum() + 1, draw_step):
                    x = val_to_x(t)
                    
                    # Draw Tick
                    tick_y = groove_rect.bottom() + 2
                    painter.drawLine(x, tick_y, x, tick_y + 5)
                    
                    # Draw Text
                    time_str = self.format_time_short(t)
                    text_rect = QRect(x - 30, tick_y + 5, 60, 15)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, time_str)

        # 4. Draw Handle
        opt.subControls = QStyle.SubControl.SC_SliderHandle
        self.style().drawComplexControl(QStyle.ComplexControl.CC_Slider, opt, painter, self)

        # 5. Draw Playhead
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
