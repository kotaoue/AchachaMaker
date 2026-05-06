"""Main application window for AchachaMaker."""

from __future__ import annotations

import os
import threading
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
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
)
from src.voicevox import VoicevoxClient


# ─── Worker signal bridge ──────────────────────────────────────────────────────


class WorkerSignals(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)


# ─── Main window ──────────────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    """Main application window for AchachaMaker."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ゲーム解説動画メーカー – AchachaMaker")
        self.resize(1280, 800)
        self._voicevox = VoicevoxClient()
        self._audio_path: Optional[str] = None
        self._speakers: list[dict] = []
        self._setup_ui()
        self._check_voicevox()

    # ── UI construction ────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Vertical)
        root_layout.addWidget(splitter, stretch=1)

        # Top half: video inputs + preview placeholder
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        top_layout.addWidget(self._build_video_panel(), stretch=1)
        top_layout.addWidget(self._build_preview_panel(), stretch=2)

        splitter.addWidget(top_widget)

        # Bottom half: timeline + edit panel
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(4)

        bottom_layout.addWidget(self._build_timeline_panel(), stretch=2)
        bottom_layout.addWidget(self._build_edit_panel(), stretch=1)

        splitter.addWidget(bottom_widget)
        splitter.setSizes([300, 500])

        # Export button
        export_btn = QPushButton("📤  書き出す")
        export_btn.setFixedHeight(40)
        export_btn.setFont(QFont("sans-serif", 12, QFont.Weight.Bold))
        export_btn.clicked.connect(self._on_export)
        root_layout.addWidget(export_btn)

        # Status bar
        self.statusBar().showMessage("準備完了")

    def _build_video_panel(self) -> QGroupBox:
        box = QGroupBox("動画ファイル")
        layout = QFormLayout(box)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Video 1
        self._video1_path = QLineEdit()
        self._video1_path.setPlaceholderText("動画ファイル 1 のパス")
        btn1 = QPushButton("参照…")
        btn1.clicked.connect(lambda: self._browse_video(self._video1_path, 0))
        row1 = QWidget()
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.addWidget(self._video1_path)
        row1_layout.addWidget(btn1)
        layout.addRow("映像 1:", row1)

        self._video1_start = QDoubleSpinBox()
        self._video1_start.setRange(0, 9999)
        self._video1_start.setSuffix(" 秒")
        self._video1_start.setDecimals(2)
        layout.addRow("開始位置 1:", self._video1_start)

        # Video 2
        self._video2_path = QLineEdit()
        self._video2_path.setPlaceholderText("動画ファイル 2 のパス")
        btn2 = QPushButton("参照…")
        btn2.clicked.connect(lambda: self._browse_video(self._video2_path, 1))
        row2 = QWidget()
        row2_layout = QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.addWidget(self._video2_path)
        row2_layout.addWidget(btn2)
        layout.addRow("映像 2:", row2)

        self._video2_start = QDoubleSpinBox()
        self._video2_start.setRange(0, 9999)
        self._video2_start.setSuffix(" 秒")
        self._video2_start.setDecimals(2)
        layout.addRow("開始位置 2:", self._video2_start)

        # Layout selector
        self._layout_combo = QComboBox()
        self._layout_combo.addItems(["左右 (side by side)", "上下 (top/bottom)"])
        layout.addRow("レイアウト:", self._layout_combo)

        # Duration
        self._duration_spin = QDoubleSpinBox()
        self._duration_spin.setRange(1, 3600)
        self._duration_spin.setValue(60)
        self._duration_spin.setSuffix(" 秒")
        self._duration_spin.valueChanged.connect(
            lambda v: self._timeline.set_duration(v)
        )
        layout.addRow("書き出し時間:", self._duration_spin)

        return box

    def _build_preview_panel(self) -> QGroupBox:
        box = QGroupBox("プレビュー")
        layout = QVBoxLayout(box)

        self._preview_label = QLabel("動画ファイルを読み込んでください")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(
            "background: #11111B; color: #585B70; border-radius: 4px;"
        )
        self._preview_label.setMinimumHeight(200)
        layout.addWidget(self._preview_label, stretch=1)

        return box

    def _build_timeline_panel(self) -> QGroupBox:
        box = QGroupBox("タイムライン  （スクロールでズーム、クリップをドラッグで移動）")
        layout = QVBoxLayout(box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._timeline = TimelineWidget()
        self._timeline.set_duration(self._duration_spin.value() if hasattr(self, "_duration_spin") else 60)
        self._timeline.playhead_moved.connect(self._on_playhead_moved)
        self._timeline.clip_moved.connect(self._on_clip_moved)
        scroll.setWidget(self._timeline)

        layout.addWidget(scroll)
        return box

    def _build_edit_panel(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_subtitle_group())
        layout.addWidget(self._build_voicevox_group())

        return container

    def _build_subtitle_group(self) -> QGroupBox:
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

        # Background
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

    # ── Slot implementations ───────────────────────────────────────────────

    def _browse_video(self, line_edit: QLineEdit, clip_index: int) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "動画ファイルを選択",
            "",
            "動画ファイル (*.mp4 *.mov *.avi *.mkv *.webm);;すべてのファイル (*)",
        )
        if not path:
            return
        line_edit.setText(path)
        # Add/update clip in timeline
        label = os.path.basename(path)
        start_spin = self._video1_start if clip_index == 0 else self._video2_start
        new_clip = TimelineClip(
            label=label,
            start=start_spin.value(),
            duration=60.0,  # placeholder; would use ffprobe in full version
            row=clip_index,
        )
        # Replace existing clip for this row
        self._timeline.clips = [c for c in self._timeline.clips if c.row != clip_index]
        self._timeline.add_clip(new_clip)
        self.statusBar().showMessage(f"映像{clip_index + 1}: {label}")

    def _browse_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "背景画像を選択",
            "",
            "画像ファイル (*.png *.jpg *.jpeg *.bmp *.gif);;すべてのファイル (*)",
        )
        if path:
            self._bg_path.setText(path)

    def _on_add_subtitle(self) -> None:
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
        self.statusBar().showMessage(f'テロップ追加: "{text}"')

    def _on_add_background(self) -> None:
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
        self.statusBar().showMessage(f"背景追加: {os.path.basename(path)}")

    def _check_voicevox(self) -> None:
        if self._voicevox.is_available():
            self._refresh_speakers()

    def _refresh_speakers(self) -> None:
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
            speaker_id = 1  # default

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
        self._audio_path = path
        start = self._vv_start.value()
        audio = TimelineAudio(label=os.path.basename(path), start=start, duration=5.0)
        self._timeline.add_audio(audio)
        self._vv_status.setText(f"生成完了: {os.path.basename(path)}")
        self.statusBar().showMessage("音声生成完了")

    def _on_playhead_moved(self, time: float) -> None:
        minutes = int(time) // 60
        secs = int(time) % 60
        self.statusBar().showMessage(f"再生位置: {minutes}:{secs:02d}")

    def _on_clip_moved(self, index: int, new_start: float) -> None:
        which = "映像1" if index == 0 else "映像2"
        self.statusBar().showMessage(f"{which} 開始位置: {new_start:.2f} 秒")

    def _on_export(self) -> None:
        v1 = self._video1_path.text().strip()
        v2 = self._video2_path.text().strip()

        if not v1 or not v2:
            QMessageBox.warning(self, "エラー", "動画ファイルを 2 本選択してください。")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "書き出し先を選択",
            "output.mp4",
            "MP4 ファイル (*.mp4)",
        )
        if not out_path:
            return

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

        config = VideoExportConfig(
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

        t = threading.Thread(target=run, daemon=True)
        t.start()
