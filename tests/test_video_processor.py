"""Unit tests for the video_processor module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.video_processor import (
    SubtitleEntry,
    VideoExportConfig,
    _escape_drawtext,
    build_ffmpeg_command,
    export_video,
)


class TestEscapeDrawtext:
    def test_plain_text(self):
        assert _escape_drawtext("hello") == "hello"

    def test_escape_single_quote(self):
        assert _escape_drawtext("it's") == "it\\'s"

    def test_escape_colon(self):
        assert _escape_drawtext("a:b") == "a\\:b"

    def test_escape_backslash(self):
        assert _escape_drawtext("a\\b") == "a\\\\b"

    def test_combined(self):
        result = _escape_drawtext("a:b's\\c")
        assert "\\\\" in result  # backslash escaped
        assert "\\'" in result   # quote escaped
        assert "\\:" in result   # colon escaped


class TestBuildFfmpegCommand:
    def _make_config(self, **kwargs) -> VideoExportConfig:
        defaults = dict(
            video1_path="/tmp/v1.mp4",
            video2_path="/tmp/v2.mp4",
            output_path="/tmp/out.mp4",
        )
        defaults.update(kwargs)
        return VideoExportConfig(**defaults)

    def test_basic_command_structure(self):
        config = self._make_config()
        cmd = build_ffmpeg_command(config)
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert "/tmp/v1.mp4" in cmd
        assert "/tmp/v2.mp4" in cmd
        assert "/tmp/out.mp4" in cmd

    def test_side_by_side_uses_hstack(self):
        config = self._make_config(layout="side_by_side")
        cmd = build_ffmpeg_command(config)
        fc_idx = cmd.index("-filter_complex")
        fc = cmd[fc_idx + 1]
        assert "hstack" in fc

    def test_top_bottom_uses_vstack(self):
        config = self._make_config(layout="top_bottom")
        cmd = build_ffmpeg_command(config)
        fc_idx = cmd.index("-filter_complex")
        fc = cmd[fc_idx + 1]
        assert "vstack" in fc

    def test_subtitle_appears_in_filter(self):
        sub = SubtitleEntry(text="テスト", start_time=1.0, end_time=3.0)
        config = self._make_config(subtitles=[sub])
        cmd = build_ffmpeg_command(config)
        fc_idx = cmd.index("-filter_complex")
        fc = cmd[fc_idx + 1]
        assert "drawtext" in fc
        assert "テスト" in fc

    def test_audio_input_added_when_provided(self):
        config = self._make_config(audio_path="/tmp/audio.wav")
        cmd = build_ffmpeg_command(config)
        assert "/tmp/audio.wav" in cmd
        assert "-c:a" in cmd
        assert "aac" in cmd

    def test_no_audio_when_not_provided(self):
        config = self._make_config(audio_path=None)
        cmd = build_ffmpeg_command(config)
        assert "-an" in cmd

    def test_video_start_times_in_ss_flags(self):
        config = self._make_config(video1_start=10.0, video2_start=20.0)
        cmd = build_ffmpeg_command(config)
        # Each -ss should appear before the corresponding -i
        ss_indices = [i for i, v in enumerate(cmd) if v == "-ss"]
        assert len(ss_indices) >= 2
        assert cmd[ss_indices[0] + 1] == "10.0"
        assert cmd[ss_indices[1] + 1] == "20.0"

    def test_duration_flag(self):
        config = self._make_config(duration=30.0)
        cmd = build_ffmpeg_command(config)
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "30.0"

    def test_output_codec_is_libx264(self):
        config = self._make_config()
        cmd = build_ffmpeg_command(config)
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "libx264"

    def test_multiple_subtitles(self):
        subs = [
            SubtitleEntry(text="Sub 1", start_time=0, end_time=2),
            SubtitleEntry(text="Sub 2", start_time=3, end_time=5),
        ]
        config = self._make_config(subtitles=subs)
        cmd = build_ffmpeg_command(config)
        fc_idx = cmd.index("-filter_complex")
        fc = cmd[fc_idx + 1]
        assert fc.count("drawtext") == 2


class TestExportVideo:
    def test_calls_subprocess_run(self):
        config = VideoExportConfig(
            video1_path="/tmp/v1.mp4",
            video2_path="/tmp/v2.mp4",
            output_path="/tmp/out.mp4",
        )
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        with patch("src.video_processor.subprocess.run", return_value=mock_result) as mock_run:
            result = export_video(config)
            mock_run.assert_called_once()
            assert result is mock_result

    def test_raises_on_ffmpeg_failure(self):
        config = VideoExportConfig(
            video1_path="/nonexistent.mp4",
            video2_path="/nonexistent2.mp4",
            output_path="/tmp/out.mp4",
        )
        with patch("src.video_processor.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg")
            with pytest.raises(subprocess.CalledProcessError):
                export_video(config)
