"""Timeline widget for displaying and editing video clips, subtitles, and backgrounds."""

from __future__ import annotations

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
    QWheelEvent,
)
from PyQt6.QtWidgets import QWidget


# ─── Data models ──────────────────────────────────────────────────────────────


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


# ─── Timeline widget ───────────────────────────────────────────────────────────


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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.clips: list[TimelineClip] = []
        self.subtitles: list[TimelineSubtitle] = []
        self.backgrounds: list[TimelineBackground] = []
        self.audios: list[TimelineAudio] = []

        self.duration: float = 120.0  # timeline total length in seconds
        self.playhead: float = 0.0  # current playhead position in seconds
        self._pixels_per_second: float = 80.0

        self._drag_target: Optional[object] = None  # item being dragged
        self._drag_start_x: int = 0
        self._drag_start_time: float = 0.0

        self.setMinimumHeight(
            _HEADER_HEIGHT + _ROW_HEIGHT * len(_ROW_LABELS) + 20
        )
        self.setMouseTracking(True)

    # ── Public helpers ──────────────────────────────────────────────────────

    def set_duration(self, seconds: float) -> None:
        self.duration = max(1.0, seconds)
        self.update()

    def set_playhead(self, time: float) -> None:
        self.playhead = max(0.0, min(time, self.duration))
        self.update()

    def add_clip(self, clip: TimelineClip) -> None:
        self.clips.append(clip)
        self.update()

    def add_subtitle(self, sub: TimelineSubtitle) -> None:
        self.subtitles.append(sub)
        self.update()

    def add_background(self, bg: TimelineBackground) -> None:
        self.backgrounds.append(bg)
        self.update()

    def add_audio(self, audio: TimelineAudio) -> None:
        self.audios.append(audio)
        self.update()

    def clear(self) -> None:
        self.clips.clear()
        self.subtitles.clear()
        self.backgrounds.clear()
        self.audios.clear()
        self.update()

    # ── Coordinate helpers ──────────────────────────────────────────────────

    def _time_to_x(self, t: float) -> int:
        return _LABEL_WIDTH + int(t * self._pixels_per_second)

    def _x_to_time(self, x: int) -> float:
        return max(0.0, (x - _LABEL_WIDTH) / self._pixels_per_second)

    def _row_to_y(self, row: int) -> int:
        return _HEADER_HEIGHT + row * _ROW_HEIGHT

    def _total_width(self) -> int:
        return _LABEL_WIDTH + int(self.duration * self._pixels_per_second) + 40

    # ── Painting ────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = QColor("#1E1E2E")
        painter.fillRect(self.rect(), bg_color)

        self._draw_ruler(painter)
        self._draw_rows(painter)
        self._draw_clips(painter)
        self._draw_subtitles(painter)
        self._draw_backgrounds(painter)
        self._draw_audios(painter)
        self._draw_playhead(painter)

    def _draw_ruler(self, painter: QPainter) -> None:
        ruler_color = QColor("#313244")
        painter.fillRect(0, 0, self.width(), _HEADER_HEIGHT, ruler_color)

        text_pen = QPen(QColor("#CDD6F4"))
        tick_pen = QPen(QColor("#585B70"))
        painter.setFont(QFont("monospace", 9))

        step = 5.0  # seconds between labels – adapt to zoom
        if self._pixels_per_second > 100:
            step = 1.0
        elif self._pixels_per_second > 40:
            step = 2.0

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
        even_color = QColor("#181825")
        odd_color = QColor("#1E1E2E")
        label_pen = QPen(QColor("#A6ADC8"))
        sep_pen = QPen(QColor("#313244"))

        painter.setFont(QFont("sans-serif", 9))

        for row, label in enumerate(_ROW_LABELS):
            y = self._row_to_y(row)
            row_rect = QRect(0, y, self.width(), _ROW_HEIGHT)
            painter.fillRect(row_rect, even_color if row % 2 == 0 else odd_color)

            # Label
            painter.setPen(label_pen)
            painter.drawText(
                QRect(0, y, _LABEL_WIDTH - 4, _ROW_HEIGHT),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

            # Separator
            painter.setPen(sep_pen)
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
            painter.setFont(QFont("sans-serif", 9))
            painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, label)

    def _draw_clips(self, painter: QPainter) -> None:
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
        x = self._time_to_x(self.playhead)
        painter.setPen(QPen(QColor("#F38BA8"), 2))
        painter.drawLine(x, 0, x, self.height())

        # Triangle marker
        painter.setBrush(QBrush(QColor("#F38BA8")))
        painter.setPen(Qt.PenStyle.NoPen)
        tri = [
            QPointF(x - 6, 0),
            QPointF(x + 6, 0),
            QPointF(x, 10),
        ]
        from PyQt6.QtGui import QPolygonF
        painter.drawPolygon(QPolygonF(tri))

    # ── Mouse interaction ───────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.position().x()
            y = event.position().y()

            # Check if clicking on a draggable item
            target = self._hit_test(int(x), int(y))
            if target is not None:
                self._drag_target = target
                self._drag_start_x = int(x)
                if isinstance(target, TimelineClip):
                    self._drag_start_time = target.start
                elif isinstance(target, (TimelineSubtitle, TimelineBackground, TimelineAudio)):
                    self._drag_start_time = target.start
            else:
                # Move playhead
                t = self._x_to_time(int(x))
                self.set_playhead(t)
                self.playhead_moved.emit(self.playhead)
                self._drag_target = None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_target is None:
            return
        dx = int(event.position().x()) - self._drag_start_x
        dt = dx / self._pixels_per_second
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
        self._drag_target = None

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        """Zoom the timeline in/out with the scroll wheel."""
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        self._pixels_per_second = max(
            _MIN_PIXELS_PER_SECOND,
            min(_MAX_PIXELS_PER_SECOND, self._pixels_per_second * factor),
        )
        self.setMinimumWidth(self._total_width())
        self.update()

    def _hit_test(self, x: int, y: int) -> Optional[object]:
        """Return the item under the cursor, or None."""
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


import os  # noqa: E402  (placed here to avoid circular issues in the module header)
