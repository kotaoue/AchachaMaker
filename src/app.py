"""Main application window for AchachaMaker."""

from __future__ import annotations

import os
import threading
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QObject, QSettings, QSignalBlocker, QStandardPaths
from PyQt6.QtGui import QColor, QFont, QIcon, QResizeEvent, QShowEvent
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QTime

from src.config import get_font
from src.timeline import (
    TimelineAudio,
    TimelineBackground,
    TimelineClip,
    TimelineSubtitle,
    TimelineWidget,
)
from src.video_processor import (
    SubtitleEntry,
    VideoExportConfig,
    build_ffmpeg_command,
    export_video,
    probe_video,
)
from src.voicevox import VoicevoxClient

PREVIEW_ASPECT_WIDTH = 16
PREVIEW_ASPECT_HEIGHT = 9


class WorkerSignals(QObject):
    """Signal bridge for communication between worker threads and the UI."""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)


class MainWindow(QMainWindow):
    """Main application window for AchachaMaker."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ゲーム解説動画メーカー – AchachaMaker")
        self.resize(1280, 800)
        self._settings = QSettings("kotaoue", "AchachaMaker")
        self._voicevox = VoicevoxClient()
        self._audio_path: Optional[str] = None
        self._speakers: list[dict] = []
        self._setup_ui()
        self._check_voicevox()

    def _default_video_dir(self) -> str:
        """Return the user's Movies folder, falling back to the home directory."""
        movies_dirs = QStandardPaths.standardLocations(
            QStandardPaths.StandardLocation.MoviesLocation
        )
        if movies_dirs and os.path.isdir(movies_dirs[0]):
            return movies_dirs[0]
        return os.path.expanduser("~")

    def _setup_ui(self) -> None:
        """Build and wire the entire UI hierarchy."""
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Vertical)
        root_layout.addWidget(splitter, stretch=1)

        splitter.addWidget(self._build_top_panel())
        splitter.addWidget(self._build_bottom_panel())
        splitter.setSizes([300, 500])

        export_btn = QPushButton("📤  書き出す")
        export_btn.setFixedHeight(40)
        export_btn.setFont(get_font(("default", 12)))
        export_btn.font().setBold(True)
        export_btn.clicked.connect(self._on_export)
        root_layout.addWidget(export_btn)

        self.statusBar().showMessage("準備完了")

    def _build_top_panel(self) -> QWidget:
        """Build the top panel containing video inputs and the preview area."""
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self._build_video_panel(), stretch=1)
        top_layout.addWidget(self._build_preview_panel(), stretch=2)
        return top_widget

    def _build_bottom_panel(self) -> QWidget:
        """Build the bottom panel containing the timeline and the edit controls."""
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(4)
        bottom_layout.addWidget(self._build_timeline_panel(), stretch=2)
        bottom_layout.addWidget(self._build_edit_panel(), stretch=1)
        return bottom_widget

    def _build_video_panel(self) -> QGroupBox:
        """Build the video file inputs panel."""
        box = QGroupBox("動画ファイル")
        layout = QFormLayout(box)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._video1_path, row1 = self._build_video_file_row("動画ファイル 1 のパス", 0)
        layout.addRow("映像 1:", row1)
        self._video1_start = self._build_start_spinbox()
        layout.addRow("開始位置 1:", self._video1_start)

        self._video2_path, row2 = self._build_video_file_row("動画ファイル 2 のパス", 1)
        layout.addRow("映像 2:", row2)
        self._video2_start = self._build_start_spinbox()
        layout.addRow("開始位置 2:", self._video2_start)

        return box

    def _build_video_file_row(
        self, placeholder: str, clip_index: int
    ) -> tuple[QLineEdit, QWidget]:
        """Build a file path input with a browse button for a video source."""
        path_edit = QLineEdit()
        path_edit.setPlaceholderText(placeholder)
        btn = QPushButton("参照…")
        btn.clicked.connect(lambda: self._browse_video(path_edit, clip_index))
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(path_edit)
        row_layout.addWidget(btn)
        return path_edit, row

    def _build_start_spinbox(self) -> QDoubleSpinBox:
        """Build a spinbox for specifying a video start time in seconds."""
        spin = QDoubleSpinBox()
        spin.setRange(0, 9999)
        spin.setSuffix(" 秒")
        spin.setDecimals(2)
        return spin

    def _build_preview_panel(self) -> QGroupBox:
        """Build the preview panel with two side-by-side video players."""
        box = QGroupBox("プレビュー")
        layout = QVBoxLayout(box)

        self._preview_container = QWidget()
        self._preview_layout = QHBoxLayout(self._preview_container)
        self._preview_layout.setContentsMargins(0, 0, 0, 0)
        self._preview_layout.setSpacing(0)

        self._video_widget1 = QVideoWidget()
        self._video_widget1.setStyleSheet("background: #11111B;")
        self._video_widget1.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self._preview_layout.addWidget(self._video_widget1)

        self._video_widget2 = QVideoWidget()
        self._video_widget2.setStyleSheet("background: #11111B;")
        self._video_widget2.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self._preview_layout.addWidget(self._video_widget2)

        self._preview_container.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(
            self._preview_container,
            stretch=1,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        # Set up media players (audio muted; preview only)
        self._player1 = QMediaPlayer()
        self._audio_out1 = QAudioOutput()
        self._audio_out1.setVolume(0.0)
        self._player1.setAudioOutput(self._audio_out1)
        self._player1.setVideoOutput(self._video_widget1)

        self._player2 = QMediaPlayer()
        self._audio_out2 = QAudioOutput()
        self._audio_out2.setVolume(0.0)
        self._player2.setAudioOutput(self._audio_out2)
        self._player2.setVideoOutput(self._video_widget2)

        return box

    def _build_timeline_panel(self) -> QGroupBox:
        """Build the scrollable timeline panel."""
        box = QGroupBox("タイムライン  （ホイールでズーム）")
        layout = QVBoxLayout(box)

        # Zoom ratio selector and export duration
        zoom_controls = QWidget()
        zoom_layout = QHBoxLayout(zoom_controls)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_label = QLabel("ズーム:")
        self._zoom_ratio_combo = QComboBox()
        for step_seconds in (0.5, 1.0, 2.0, 5.0):
            self._zoom_ratio_combo.addItem(f"1マス {step_seconds:g}秒", step_seconds)
        self._zoom_ratio_combo.currentIndexChanged.connect(self._on_zoom_ratio_changed)
        zoom_layout.addWidget(zoom_label)
        zoom_layout.addWidget(self._zoom_ratio_combo)
        zoom_layout.addStretch()

        # Export duration (right-aligned)
        duration_label = QLabel("書き出し時間:")
        self._duration_spin = QDoubleSpinBox()
        self._duration_spin.setRange(1, 3600)
        self._duration_spin.setValue(60)
        self._duration_spin.setSuffix(" 秒")
        self._duration_spin.valueChanged.connect(
            lambda v: self._timeline.set_duration(v)
        )
        zoom_layout.addWidget(duration_label)
        zoom_layout.addWidget(self._duration_spin)
        layout.addWidget(zoom_controls)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(240)

        # Container for timeline with bottom padding
        timeline_container = QWidget()
        timeline_layout = QVBoxLayout(timeline_container)
        timeline_layout.setContentsMargins(0, 0, 0, 0)

        self._timeline = TimelineWidget()
        self._timeline.set_duration(self._duration_spin.value() if hasattr(self, "_duration_spin") else 60)
        self._timeline.playhead_moved.connect(self._on_playhead_moved)
        self._timeline.clip_moved.connect(self._on_clip_moved)
        self._timeline.zoom_ratio_changed.connect(self._sync_zoom_ratio_combo)
        timeline_layout.addWidget(self._timeline)

        self._sync_zoom_ratio_combo(self._timeline.current_zoom_step_seconds())

        timeline_layout.addSpacing(48)
        timeline_layout.addStretch()

        scroll.setWidget(timeline_container)

        layout.addWidget(scroll)
        return box

    def _build_edit_panel(self) -> QWidget:
        """Build the bottom edit panel with subtitle, background, and VOICEVOX controls."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_subtitle_group())
        layout.addWidget(self._build_voicevox_group())
        layout.addWidget(self._build_background_group())

        return container

    def _build_subtitle_group(self) -> QGroupBox:
        """Build the subtitle (telop) edit form."""
        box = QGroupBox("テロップ追加")
        layout = QFormLayout(box)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._sub_text = QLineEdit()
        self._sub_text.setPlaceholderText("字幕テキスト")
        layout.addRow("テキスト:", self._sub_text)

        self._sub_start = QDoubleSpinBox()
        self._sub_start.setRange(0, 9999)
        self._sub_start.setSuffix(" 秒")
        self._sub_start.setDecimals(2)
        layout.addRow("開始:", self._sub_start)

        self._sub_end = QDoubleSpinBox()
        self._sub_end.setRange(0, 9999)
        self._sub_end.setValue(5)
        self._sub_end.setSuffix(" 秒")
        self._sub_end.setDecimals(2)
        layout.addRow("終了:", self._sub_end)

        self._sub_size = QSpinBox()
        self._sub_size.setRange(8, 200)
        self._sub_size.setValue(40)
        layout.addRow("フォントサイズ:", self._sub_size)

        self._sub_color = QLineEdit("white")
        layout.addRow("色:", self._sub_color)

        add_btn = QPushButton("テロップ追加")
        add_btn.clicked.connect(self._on_add_subtitle)
        layout.addRow(add_btn)

        return box

    def _build_background_group(self) -> QGroupBox:
        """Build the background image edit form."""
        box = QGroupBox("背景")
        layout = QFormLayout(box)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._bg_path = QLineEdit()
        self._bg_path.setPlaceholderText("背景画像パス")
        bg_browse = QPushButton("参照…")
        bg_browse.clicked.connect(self._browse_background)
        bg_row = QWidget()
        bg_row_layout = QHBoxLayout(bg_row)
        bg_row_layout.setContentsMargins(0, 0, 0, 0)
        bg_row_layout.addWidget(self._bg_path)
        bg_row_layout.addWidget(bg_browse)
        layout.addRow("背景画像:", bg_row)

        self._layout_combo = QComboBox()
        self._layout_combo.addItems(["左右 (side by side)", "上下 (top/bottom)"])
        self._layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        layout.addRow("レイアウト:", self._layout_combo)

        self._bg_start = QDoubleSpinBox()
        self._bg_start.setRange(0, 9999)
        self._bg_start.setSuffix(" 秒")
        self._bg_start.setDecimals(2)
        layout.addRow("背景 開始:", self._bg_start)

        self._bg_end = QDoubleSpinBox()
        self._bg_end.setRange(0, 9999)
        self._bg_end.setValue(10)
        self._bg_end.setSuffix(" 秒")
        self._bg_end.setDecimals(2)
        layout.addRow("背景 終了:", self._bg_end)

        bg_add_btn = QPushButton("背景追加")
        bg_add_btn.clicked.connect(self._on_add_background)
        layout.addRow(bg_add_btn)

        return box

    def _build_voicevox_group(self) -> QGroupBox:
        """Build the VOICEVOX text-to-speech synthesis form."""
        box = QGroupBox("VOICEVOX 音声合成")
        layout = QFormLayout(box)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._vv_text = QLineEdit()
        self._vv_text.setPlaceholderText("セリフテキスト")
        layout.addRow("セリフ:", self._vv_text)

        self._vv_speaker = QComboBox()
        self._vv_speaker.addItem("（VOICEVOX が起動していません）")
        layout.addRow("キャラ:", self._vv_speaker)

        self._vv_start = QDoubleSpinBox()
        self._vv_start.setRange(0, 9999)
        self._vv_start.setSuffix(" 秒")
        self._vv_start.setDecimals(2)
        layout.addRow("配置位置:", self._vv_start)

        btn_gen = QPushButton("音声生成")
        btn_gen.clicked.connect(self._on_generate_voice)
        layout.addRow(btn_gen)

        self._vv_status = QLabel("─")
        layout.addRow("状態:", self._vv_status)

        refresh_btn = QPushButton("スピーカー更新")
        refresh_btn.clicked.connect(self._refresh_speakers)
        layout.addRow(refresh_btn)

        return box

    def _browse_video(self, line_edit: QLineEdit, clip_index: int) -> None:
        """Open a file chooser, update the path field, and refresh the timeline clip."""
        start_dir = self._settings.value("last_input_dir", self._default_video_dir())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "動画ファイルを選択",
            start_dir,
            "動画ファイル (*.mp4 *.mov *.avi *.mkv *.webm);;すべてのファイル (*)",
        )
        if not path:
            return
        self._settings.setValue("last_input_dir", os.path.dirname(path))
        line_edit.setText(path)
        self._update_timeline_clip(path, clip_index)
        self._load_preview(path, clip_index)
        self.statusBar().showMessage(f"映像{clip_index + 1}: {os.path.basename(path)}")

    def _update_timeline_clip(self, path: str, clip_index: int) -> None:
        """Replace the timeline clip for *clip_index* with one built from *path*."""
        label = os.path.basename(path)
        start_spin = self._video1_start if clip_index == 0 else self._video2_start
        duration = 60.0
        try:
            meta = probe_video(path)
            duration = max(1.0, float(meta.get("duration", 0.0)) - start_spin.value())
        except Exception:
            # Fall back to a sane default when ffprobe metadata is unavailable.
            duration = 60.0

        new_clip = TimelineClip(
            label=label,
            start=start_spin.value(),
            duration=duration,
            row=clip_index,
        )
        self._timeline.clips = [c for c in self._timeline.clips if c.row != clip_index]
        self._timeline.add_clip(new_clip)
        self._sync_timeline_and_export_duration()

    def _sync_timeline_and_export_duration(self) -> None:
        """Extend timeline/export duration to fit the longest clip or track item."""
        candidates: list[float] = []

        candidates.extend(c.start + c.duration for c in self._timeline.clips)
        candidates.extend(s.end for s in self._timeline.subtitles)
        candidates.extend(bg.end for bg in self._timeline.backgrounds)
        candidates.extend(a.start + a.duration for a in self._timeline.audios)

        required = max(candidates) if candidates else 1.0
        if self._duration_spin.value() < required:
            self._duration_spin.setValue(required)

        self._timeline.set_duration(max(self._timeline.duration, required))

    def _browse_background(self) -> None:
        """Open a file chooser and populate the background image path field."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "背景画像を選択",
            "",
            "画像ファイル (*.png *.jpg *.jpeg *.bmp *.gif);;すべてのファイル (*)",
        )
        if path:
            self._bg_path.setText(path)

    def _on_add_subtitle(self) -> None:
        """Validate the subtitle form and add a new subtitle to the timeline."""
        text = self._sub_text.text().strip()
        if not text:
            QMessageBox.warning(self, "入力エラー", "テキストを入力してください。")
            return

        sub = TimelineSubtitle(
            text=text,
            start=self._sub_start.value(),
            end=self._sub_end.value(),
            font_size=self._sub_size.value(),
            color=self._sub_color.text() or "white",
        )
        self._timeline.add_subtitle(sub)
        self._sync_timeline_and_export_duration()
        self.statusBar().showMessage(f'テロップ追加: "{text}"')

    def _on_add_background(self) -> None:
        """Validate the background form and add a background entry to the timeline."""
        path = self._bg_path.text().strip()
        if not path:
            QMessageBox.warning(self, "入力エラー", "背景画像を選択してください。")
            return

        bg = TimelineBackground(
            image_path=path,
            start=self._bg_start.value(),
            end=self._bg_end.value(),
        )
        self._timeline.add_background(bg)
        self._sync_timeline_and_export_duration()
        self.statusBar().showMessage(f"背景追加: {os.path.basename(path)}")

    def _check_voicevox(self) -> None:
        """Populate the speaker list if the VOICEVOX engine is already running."""
        if self._voicevox.is_available():
            self._refresh_speakers()

    def _refresh_speakers(self) -> None:
        """Fetch available VOICEVOX speakers and repopulate the speaker combo."""
        try:
            speakers = self._voicevox.get_speakers()
            self._speakers = speakers
            self._vv_speaker.clear()
            for sp in speakers:
                for style in sp.get("styles", []):
                    name = f"{sp['name']} – {style['name']}"
                    self._vv_speaker.addItem(name, userData=style["id"])
            self.statusBar().showMessage("VOICEVOX スピーカーを更新しました")
        except Exception as e:
            self.statusBar().showMessage(f"VOICEVOX に接続できません: {e}")

    def _on_generate_voice(self) -> None:
        """Validate the voice form and start async TTS synthesis."""
        text = self._vv_text.text().strip()
        if not text:
            QMessageBox.warning(self, "入力エラー", "セリフを入力してください。")
            return
        if not self._voicevox.is_available():
            QMessageBox.warning(
                self, "VOICEVOX エラー", "VOICEVOX エンジンが起動していません。"
            )
            return

        speaker_id = self._vv_speaker.currentData()
        if speaker_id is None:
            speaker_id = 1

        self._vv_status.setText("生成中…")
        signals = WorkerSignals()
        signals.finished.connect(self._on_voice_generated)
        signals.error.connect(lambda msg: self._vv_status.setText(f"エラー: {msg}"))

        def run() -> None:
            try:
                path = self._voicevox.synthesize_to_file(text, int(speaker_id))
                signals.finished.emit(path)
            except Exception as e:
                signals.error.emit(str(e))

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _on_voice_generated(self, path: str) -> None:
        """Update the timeline and status bar after TTS synthesis completes."""
        self._audio_path = path
        start = self._vv_start.value()
        audio = TimelineAudio(label=os.path.basename(path), start=start, duration=5.0)
        self._timeline.add_audio(audio)
        self._sync_timeline_and_export_duration()
        self._vv_status.setText(f"生成完了: {os.path.basename(path)}")
        self.statusBar().showMessage("音声生成完了")

    def _load_preview(self, path: str, clip_index: int) -> None:
        """Load a video file into the corresponding preview player and seek to start."""
        player = self._player1 if clip_index == 0 else self._player2
        start_spin = self._video1_start if clip_index == 0 else self._video2_start
        player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
        start_ms = int(start_spin.value() * 1000)

        def _seek_after_load(state: QMediaPlayer.MediaStatus) -> None:
            if state in (
                QMediaPlayer.MediaStatus.BufferedMedia,
                QMediaPlayer.MediaStatus.LoadedMedia,
            ):
                player.setPosition(start_ms)
                player.pause()
                player.mediaStatusChanged.disconnect(_seek_after_load)

        player.mediaStatusChanged.connect(_seek_after_load)

    def _on_playhead_moved(self, time: float) -> None:
        """Seek both preview players to the playhead time and update the status bar."""
        for player, spin in [
            (self._player1, self._video1_start),
            (self._player2, self._video2_start),
        ]:
            if player.source().isValid():
                pos_ms = int((spin.value() + time) * 1000)
                player.setPosition(pos_ms)
                player.pause()
        minutes = int(time) // 60
        secs = int(time) % 60
        self.statusBar().showMessage(f"再生位置: {minutes}:{secs:02d}")

    def _on_clip_moved(self, index: int, new_start: float) -> None:
        """Show the updated clip start time in the status bar."""
        which = "映像1" if index == 0 else "映像2"
        self._sync_timeline_and_export_duration()
        self.statusBar().showMessage(f"{which} 開始位置: {new_start:.2f} 秒")

    def _on_zoom_ratio_changed(self, index: int) -> None:
        """Update timeline zoom ratio when user changes the dropdown."""
        step_seconds = self._zoom_ratio_combo.itemData(index)
        if step_seconds is None:
            return
        self._timeline.set_zoom_step_seconds(float(step_seconds))

    def _sync_zoom_ratio_combo(self, step_seconds: float) -> None:
        """Keep the zoom ratio dropdown in sync with wheel-based zoom changes."""
        for index in range(self._zoom_ratio_combo.count()):
            if float(self._zoom_ratio_combo.itemData(index)) == step_seconds:
                blocker = QSignalBlocker(self._zoom_ratio_combo)
                self._zoom_ratio_combo.setCurrentIndex(index)
                del blocker
                break

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep the preview canvas aligned to the exported output aspect ratio."""
        super().resizeEvent(event)
        self._update_preview_container_size()

    def showEvent(self, event: QShowEvent) -> None:
        """Size the preview canvas after initial layout is established."""
        super().showEvent(event)
        self._update_preview_container_size()

    def _update_preview_container_size(self) -> None:
        """Resize preview canvas to 16:9 so preview layout matches export output."""
        if not hasattr(self, "_preview_container"):
            return
        parent = self._preview_container.parentWidget()
        if parent is None:
            return

        available = parent.contentsRect()
        available_width = max(1, available.width())
        available_height = max(1, available.height())
        target_width = available_width
        target_height = int((target_width * PREVIEW_ASPECT_HEIGHT) / PREVIEW_ASPECT_WIDTH)
        if target_height > available_height:
            target_height = available_height
            target_width = int((target_height * PREVIEW_ASPECT_WIDTH) / PREVIEW_ASPECT_HEIGHT)
        self._preview_container.setFixedSize(target_width, target_height)

    def _on_layout_changed(self, index: int) -> None:
        """Apply selected layout orientation to the preview area."""
        direction = (
            QBoxLayout.Direction.LeftToRight
            if index == 0
            else QBoxLayout.Direction.TopToBottom
        )
        self._preview_layout.setDirection(direction)
        self._update_preview_container_size()


    def _on_export(self) -> None:
        """Validate inputs, collect configuration, and run ffmpeg export asynchronously."""
        v1 = self._video1_path.text().strip()
        v2 = self._video2_path.text().strip()

        if not v1 or not v2:
            QMessageBox.warning(self, "エラー", "動画ファイルを 2 本選択してください。")
            return

        last_output_dir = self._settings.value("last_output_dir", self._default_video_dir())
        default_output = os.path.join(last_output_dir, "output.mp4")
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "書き出し先を選択",
            default_output,
            "MP4 ファイル (*.mp4)",
        )
        if not out_path:
            return
        self._settings.setValue("last_output_dir", os.path.dirname(out_path))

        config = self._build_export_config(v1, v2, out_path)
        self._run_export_async(config, out_path)

    def _build_export_config(
        self, v1: str, v2: str, out_path: str
    ) -> VideoExportConfig:
        """Assemble a :class:`VideoExportConfig` from the current UI state."""
        layout_idx = self._layout_combo.currentIndex()
        layout = "side_by_side" if layout_idx == 0 else "top_bottom"

        subtitles = [
            SubtitleEntry(
                text=sub.text,
                start_time=sub.start,
                end_time=sub.end,
                font_size=sub.font_size,
                color=sub.color,
            )
            for sub in self._timeline.subtitles
        ]

        return VideoExportConfig(
            video1_path=v1,
            video2_path=v2,
            video1_start=self._video1_start.value(),
            video2_start=self._video2_start.value(),
            output_path=out_path,
            layout=layout,
            duration=self._duration_spin.value(),
            subtitles=subtitles,
            audio_path=self._audio_path,
        )

    def _run_export_async(self, config: VideoExportConfig, out_path: str) -> None:
        """Start ffmpeg export in a background thread and wire status callbacks."""
        self.statusBar().showMessage("書き出し中…")
        signals = WorkerSignals()
        signals.finished.connect(
            lambda _: self.statusBar().showMessage(f"書き出し完了: {out_path}")
        )
        signals.error.connect(
            lambda msg: QMessageBox.critical(self, "書き出しエラー", msg)
        )

        def run() -> None:
            try:
                export_video(config)
                signals.finished.emit(out_path)
            except Exception as e:
                signals.error.emit(str(e))

        t = threading.Thread(target=run, daemon=False)
        t.start()
