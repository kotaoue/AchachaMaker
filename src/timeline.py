"""Timeline widget for displaying and editing video clips, subtitles, and backgrounds."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import (
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PyQt6.QtWidgets import QWidget

from src.config import get_font


@dataclass
class TimelineClip:
    """Represents one video clip on the timeline."""

    label: str
    start: float  # seconds from beginning of timeline
    duration: float  # seconds
    color: QColor = field(default_factory=lambda: QColor("#4A90D9"))
    row: int = 0  # which track row (0 = first video, 1 = second video, …)


@dataclass
class TimelineSubtitle:
    """Represents a subtitle block on the timeline."""

    text: str
    start: float
    end: float
    font_size: int = 40
    color: str = "white"
    row: int = 2


@dataclass
class TimelineBackground:
    """Represents a background image block on the timeline."""

    image_path: str
    start: float
    end: float
    row: int = 3


@dataclass
class TimelineAudio:
    """Represents an audio clip on the timeline."""

    label: str
    start: float
    duration: float
    row: int = 4


_ROW_LABELS = ["映像1", "映像2", "テロップ", "背景", "音声"]
_ROW_COLORS = [
    QColor("#4A90D9"),  # video 1 – blue
    QColor("#7B68EE"),  # video 2 – medium slate blue
    QColor("#F5A623"),  # subtitle – orange
    QColor("#7ED321"),  # background – green
    QColor("#D0021B"),  # audio – red
]

_HEADER_HEIGHT = 30  # pixels for time ruler
_ROW_HEIGHT = 36  # pixels per track row
_LABEL_WIDTH = 60  # pixels for row labels on the left
_MIN_PIXELS_PER_SECOND = 20
_MAX_PIXELS_PER_SECOND = 300
_ZOOM_STEP_SECONDS = (0.5, 1.0, 2.0, 5.0)


class TimelineWidget(QWidget):
    """
    A custom timeline widget that displays clips on multiple rows.

    Signals
    -------
    playhead_moved(float)
        Emitted when the user clicks/drags the playhead to a new position
        (time in seconds).
    clip_moved(int, float)
        Emitted when a clip is dragged to a new start time.
        Args: clip index in clips list, new start time in seconds.
    subtitle_moved(int, float, float)
        Emitted when a subtitle block is moved. Args: index, new start, new end.
    """

    playhead_moved = pyqtSignal(float)
    clip_moved = pyqtSignal(int, float)
    subtitle_moved = pyqtSignal(int, float, float)
    zoom_ratio_changed = pyqtSignal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.clips: list[TimelineClip] = []
        self.subtitles: list[TimelineSubtitle] = []
        self.backgrounds: list[TimelineBackground] = []
        self.audios: list[TimelineAudio] = []

        self.duration: float = 120.0  # timeline total length in seconds
        self.playhead: float = 0.0  # current playhead position in seconds
        self._pixels_per_second: float = 80.0
        self._zoom_step_seconds: float = 2.0

        self._drag_target: Optional[object] = None  # item being dragged
        self._drag_start_x: int = 0
        self._drag_start_time: float = 0.0

        self.setMinimumHeight(
            _HEADER_HEIGHT + _ROW_HEIGHT * len(_ROW_LABELS) + 20
        )
        self.setMouseTracking(True)

    def set_duration(self, seconds: float) -> None:
        """Set the total visible duration of the timeline in seconds."""
        self.duration = max(1.0, seconds)
        self.update()

    def set_playhead(self, time: float) -> None:
        """Move the playhead to *time* (clamped to [0, duration])."""
        self.playhead = max(0.0, min(time, self.duration))
        self.update()

    def current_zoom_step_seconds(self) -> float:
        """Return the current major ruler interval in seconds."""
        return self._zoom_step_seconds

    def set_zoom_step_seconds(self, seconds: float) -> None:
        """Set the major ruler interval and adjust zoom to a matching scale."""
        step = min(_ZOOM_STEP_SECONDS, key=lambda candidate: abs(candidate - seconds))
        self._zoom_step_seconds = step

        target_pixels_per_second = {
            0.5: 220.0,
            1.0: 120.0,
            2.0: 80.0,
            5.0: 32.0,
        }[step]
        self._pixels_per_second = max(
            _MIN_PIXELS_PER_SECOND,
            min(_MAX_PIXELS_PER_SECOND, target_pixels_per_second),
        )
        self.setMinimumWidth(self._total_width())
        self.zoom_ratio_changed.emit(self._zoom_step_seconds)
        self.update()

    def _zoom_step_for_pixels_per_second(self, pixels_per_second: float) -> float:
        """Return the ruler interval that best matches the current zoom level."""
        if pixels_per_second >= 170.0:
            return 0.5
        if pixels_per_second >= 95.0:
            return 1.0
        if pixels_per_second >= 48.0:
            return 2.0
        return 5.0

    def add_clip(self, clip: TimelineClip) -> None:
        """Append *clip* to the timeline and repaint."""
        self.clips.append(clip)
        self.update()

    def add_subtitle(self, sub: TimelineSubtitle) -> None:
        """Append *sub* to the subtitle list and repaint."""
        self.subtitles.append(sub)
        self.update()

    def add_background(self, bg: TimelineBackground) -> None:
        """Append *bg* to the background list and repaint."""
        self.backgrounds.append(bg)
        self.update()

    def add_audio(self, audio: TimelineAudio) -> None:
        """Append *audio* to the audio list and repaint."""
        self.audios.append(audio)
        self.update()

    def clear(self) -> None:
        """Remove all items from every track and repaint."""
        self.clips.clear()
        self.subtitles.clear()
        self.backgrounds.clear()
        self.audios.clear()
        self.update()

    def _time_to_x(self, t: float) -> int:
        """Convert a timeline time in seconds to a pixel x-coordinate."""
        return _LABEL_WIDTH + int(t * self._pixels_per_second)

    def _x_to_time(self, x: int) -> float:
        """Convert a pixel x-coordinate to a timeline time in seconds."""
        return max(0.0, (x - _LABEL_WIDTH) / self._pixels_per_second)

    def _row_to_y(self, row: int) -> int:
        """Return the top y-coordinate of a track row."""
        return _HEADER_HEIGHT + row * _ROW_HEIGHT

    def _total_width(self) -> int:
        """Return the minimum widget width needed to display the full timeline."""
        return _LABEL_WIDTH + int(self.duration * self._pixels_per_second) + 40

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Render the complete timeline: ruler, rows, clips, and playhead."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor("#1E1E2E"))

        self._draw_ruler(painter)
        self._draw_rows(painter)
        self._draw_clips(painter)
        self._draw_subtitles(painter)
        self._draw_backgrounds(painter)
        self._draw_audios(painter)
        self._draw_playhead(painter)

    def _draw_ruler(self, painter: QPainter) -> None:
        """Draw the time ruler at the top of the widget."""
        painter.fillRect(0, 0, self.width(), _HEADER_HEIGHT, QColor("#313244"))

        text_pen = QPen(QColor("#CDD6F4"))
        tick_pen = QPen(QColor("#585B70"))
        painter.setFont(QFont("monospace", 9))

        step = self._zoom_step_seconds

        t = 0.0
        while t <= self.duration:
            x = self._time_to_x(t)
            painter.setPen(tick_pen)
            painter.drawLine(x, _HEADER_HEIGHT - 8, x, _HEADER_HEIGHT)
            painter.setPen(text_pen)
            minutes = int(t) // 60
            secs = int(t) % 60
            painter.drawText(x + 2, _HEADER_HEIGHT - 10, f"{minutes}:{secs:02d}")
            t += step

    def _draw_rows(self, painter: QPainter) -> None:
        """Draw alternating row backgrounds, labels, and separators."""
        painter.setFont(get_font(("default", 9)))
        for row, label in enumerate(_ROW_LABELS):
            y = self._row_to_y(row)
            bg = QColor("#181825") if row % 2 == 0 else QColor("#1E1E2E")
            painter.fillRect(QRect(0, y, self.width(), _ROW_HEIGHT), bg)
            self._draw_row_label(painter, label, y)
            self._draw_row_separator(painter, y)

    def _draw_row_label(self, painter: QPainter, label: str, y: int) -> None:
        """Draw the track name label in the left gutter at row y."""
        painter.setPen(QPen(QColor("#A6ADC8")))
        painter.drawText(
            QRect(0, y, _LABEL_WIDTH - 4, _ROW_HEIGHT),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            label,
        )

    def _draw_row_separator(self, painter: QPainter, y: int) -> None:
        """Draw a horizontal separator line at the bottom of the row at y."""
        painter.setPen(QPen(QColor("#313244")))
        painter.drawLine(0, y + _ROW_HEIGHT - 1, self.width(), y + _ROW_HEIGHT - 1)

    def _draw_block(
        self,
        painter: QPainter,
        row: int,
        start: float,
        end: float,
        color: QColor,
        label: str,
    ) -> None:
        """Draw a rounded rectangle block for a clip, subtitle, or background."""
        x1 = self._time_to_x(start)
        x2 = self._time_to_x(end)
        y = self._row_to_y(row) + 4
        h = _ROW_HEIGHT - 8

        rect = QRectF(x1, y, max(4, x2 - x1), h)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.lighter(150), 1))
        painter.drawRoundedRect(rect, 4, 4)

        if x2 - x1 > 20:
            painter.setPen(QPen(QColor("#1E1E2E")))
            painter.setFont(get_font(("default", 9)))
            painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, label)

    def _draw_clips(self, painter: QPainter) -> None:
        """Draw all video clip blocks onto the timeline."""
        for clip in self.clips:
            self._draw_block(
                painter,
                clip.row,
                clip.start,
                clip.start + clip.duration,
                _ROW_COLORS[min(clip.row, len(_ROW_COLORS) - 1)],
                clip.label,
            )

    def _draw_subtitles(self, painter: QPainter) -> None:
        """Draw all subtitle blocks onto the timeline."""
        for sub in self.subtitles:
            self._draw_block(
                painter,
                sub.row,
                sub.start,
                sub.end,
                _ROW_COLORS[2],
                sub.text,
            )

    def _draw_backgrounds(self, painter: QPainter) -> None:
        """Draw all background image blocks onto the timeline."""
        for bg in self.backgrounds:
            label = os.path.basename(bg.image_path) if bg.image_path else "背景"
            self._draw_block(
                painter,
                bg.row,
                bg.start,
                bg.end,
                _ROW_COLORS[3],
                label,
            )

    def _draw_audios(self, painter: QPainter) -> None:
        """Draw all audio clip blocks onto the timeline."""
        for audio in self.audios:
            self._draw_block(
                painter,
                audio.row,
                audio.start,
                audio.start + audio.duration,
                _ROW_COLORS[4],
                audio.label,
            )

    def _draw_playhead(self, painter: QPainter) -> None:
        """Draw the playhead line and its triangular top marker."""
        x = self._time_to_x(self.playhead)
        self._draw_playhead_line(painter, x)
        self._draw_playhead_marker(painter, x)

    def _draw_playhead_line(self, painter: QPainter, x: int) -> None:
        """Draw the vertical playhead line spanning the full widget height."""
        painter.setPen(QPen(QColor("#F38BA8"), 4))
        painter.drawLine(x, 0, x, self.height())

    def _draw_playhead_marker(self, painter: QPainter, x: int) -> None:
        """Draw the downward-pointing triangle at the top of the playhead."""
        painter.setBrush(QBrush(QColor("#F38BA8")))
        painter.setPen(Qt.PenStyle.NoPen)
        tri = [QPointF(x - 8, 0), QPointF(x + 8, 0), QPointF(x, 12)]
        painter.drawPolygon(QPolygonF(tri))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        """Start dragging an item or move the playhead on left-click."""
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x, y = int(event.position().x()), int(event.position().y())
        target = self._hit_test(x, y)
        if target is not None:
            self._start_drag(target, x)
        else:
            self._move_playhead_to(x)

    def _start_drag(self, target: object, x: int) -> None:
        """Record drag state for *target* starting at pixel column *x*."""
        self._drag_target = target
        self._drag_start_x = x
        if target is self:
            # Playhead dragging
            self._drag_start_time = self.playhead
        else:
            self._drag_start_time = target.start  # type: ignore[attr-defined]

    def _move_playhead_to(self, x: int) -> None:
        """Move the playhead to the time corresponding to pixel column *x*."""
        t = self._x_to_time(x)
        self.set_playhead(t)
        self.playhead_moved.emit(self.playhead)
        self._drag_target = None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        """Update the position of the item being dragged."""
        if self._drag_target is None:
            return
        dx = int(event.position().x()) - self._drag_start_x
        dt = dx / self._pixels_per_second

        if self._drag_target is self:
            # Playhead dragging
            new_playhead = max(0.0, min(self._drag_start_time + dt, self.duration))
            self.set_playhead(new_playhead)
            self.playhead_moved.emit(self.playhead)
        else:
            new_start = max(0.0, self._drag_start_time + dt)

            if isinstance(self._drag_target, TimelineClip):
                idx = self.clips.index(self._drag_target)
                self._drag_target.start = new_start
                self.clip_moved.emit(idx, new_start)
            elif isinstance(self._drag_target, TimelineSubtitle):
                idx = self.subtitles.index(self._drag_target)
                dur = self._drag_target.end - self._drag_target.start
                self._drag_target.start = new_start
                self._drag_target.end = new_start + dur
                self.subtitle_moved.emit(idx, new_start, new_start + dur)
            elif isinstance(self._drag_target, TimelineBackground):
                dur = self._drag_target.end - self._drag_target.start
                self._drag_target.start = new_start
                self._drag_target.end = new_start + dur
            elif isinstance(self._drag_target, TimelineAudio):
                self._drag_target.start = new_start

            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        """End any active drag operation."""
        self._drag_target = None

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        """Zoom the timeline in/out with the scroll wheel."""
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9

        self._pixels_per_second = max(
            _MIN_PIXELS_PER_SECOND,
            min(_MAX_PIXELS_PER_SECOND, self._pixels_per_second * factor),
        )

        zoom_step_seconds = self._zoom_step_for_pixels_per_second(self._pixels_per_second)
        if zoom_step_seconds != self._zoom_step_seconds:
            self._zoom_step_seconds = zoom_step_seconds
            self.zoom_ratio_changed.emit(self._zoom_step_seconds)

        self.setMinimumWidth(self._total_width())
        self.update()

    def _hit_test(self, x: int, y: int) -> Optional[object]:
        """Return the item under the cursor, or None."""
        # Check if playhead is clicked (wider hit area for easier interaction)
        playhead_x = self._time_to_x(self.playhead)
        if abs(x - playhead_x) <= 6 and y < _HEADER_HEIGHT:
            return self

        for clip in self.clips:
            row_y = self._row_to_y(clip.row)
            x1 = self._time_to_x(clip.start)
            x2 = self._time_to_x(clip.start + clip.duration)
            if x1 <= x <= x2 and row_y <= y <= row_y + _ROW_HEIGHT:
                return clip

        for sub in self.subtitles:
            row_y = self._row_to_y(sub.row)
            x1 = self._time_to_x(sub.start)
            x2 = self._time_to_x(sub.end)
            if x1 <= x <= x2 and row_y <= y <= row_y + _ROW_HEIGHT:
                return sub

        for bg in self.backgrounds:
            row_y = self._row_to_y(bg.row)
            x1 = self._time_to_x(bg.start)
            x2 = self._time_to_x(bg.end)
            if x1 <= x <= x2 and row_y <= y <= row_y + _ROW_HEIGHT:
                return bg

        for audio in self.audios:
            row_y = self._row_to_y(audio.row)
            x1 = self._time_to_x(audio.start)
            x2 = self._time_to_x(audio.start + audio.duration)
            if x1 <= x <= x2 and row_y <= y <= row_y + _ROW_HEIGHT:
                return audio

        return None

