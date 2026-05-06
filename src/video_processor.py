"""ffmpeg-based video processing: compositing, subtitles, and export."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SubtitleEntry:
    """A single subtitle (telop) entry."""

    text: str
    start_time: float  # seconds
    end_time: float  # seconds
    font_size: int = 40
    color: str = "white"  # ffmpeg color name or hex (e.g. "white", "0xFFFFFF")
    x: str = "(w-text_w)/2"  # drawtext x expression
    y: str = "h-th-20"  # drawtext y expression (near bottom)


@dataclass
class BackgroundEntry:
    """A background image active for a time range."""

    image_path: str
    start_time: float  # seconds
    end_time: float  # seconds


@dataclass
class VideoExportConfig:
    """Configuration for the final video export."""

    video1_path: str
    video2_path: str
    video1_start: float = 0.0  # start time in source video (seconds)
    video2_start: float = 0.0  # start time in source video (seconds)
    output_path: str = "output.mp4"
    layout: str = "side_by_side"  # "side_by_side" or "top_bottom"
    output_width: int = 1920
    output_height: int = 1080
    duration: float = 60.0  # output duration in seconds
    subtitles: list[SubtitleEntry] = field(default_factory=list)
    background_entries: list[BackgroundEntry] = field(default_factory=list)
    audio_path: Optional[str] = None  # path to VOICEVOX WAV
    audio_start: float = 0.0  # when to start the audio track (seconds)
    fps: int = 30
    video_bitrate: str = "4M"
    audio_bitrate: str = "192k"


def _escape_drawtext(text: str) -> str:
    """Escape special characters for the ffmpeg ``drawtext`` filter.

    Backslashes must be escaped before other characters to avoid
    double-escaping.
    """
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    return text


def _build_video_inputs(config: VideoExportConfig) -> list[str]:
    """Return ffmpeg input flags for the two source videos."""
    return [
        "-ss", str(config.video1_start), "-i", config.video1_path,
        "-ss", str(config.video2_start), "-i", config.video2_path,
    ]


def _build_image_inputs(
    config: VideoExportConfig, start_index: int
) -> tuple[list[str], list[int]]:
    """Return ffmpeg input flags for background images and their stream indices."""
    args: list[str] = []
    indices: list[int] = []
    for i, bg in enumerate(config.background_entries):
        args += ["-i", bg.image_path]
        indices.append(start_index + i)
    return args, indices


def _build_audio_input(
    config: VideoExportConfig, start_index: int
) -> tuple[list[str], Optional[int]]:
    """Return ffmpeg input flags for the optional audio track and its stream index.

    Returns an empty list and ``None`` when no audio path is configured.
    """
    if not config.audio_path:
        return [], None
    return ["-ss", str(config.audio_start), "-i", config.audio_path], start_index


def _build_scale_and_layout_filters(
    config: VideoExportConfig,
) -> tuple[list[str], str]:
    """Return scale/pad and stack filters that composite the two video streams.

    Each clip is letterboxed into its half of the canvas, then the two halves
    are joined with ``hstack`` (side-by-side) or ``vstack`` (top/bottom).
    Returns the filter list and the output stream label ``"combined"``.
    """
    w, h = config.output_width, config.output_height
    if config.layout == "side_by_side":
        scale_w, scale_h, stack = w // 2, h, "hstack"
    else:
        scale_w, scale_h, stack = w, h // 2, "vstack"

    pad = f"pad={scale_w}:{scale_h}:(ow-iw)/2:(oh-ih)/2"
    scale = f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=decrease"
    return [
        f"[0:v]{scale},{pad}[v0]",
        f"[1:v]{scale},{pad}[v1]",
        f"[v0][v1]{stack}=inputs=2[combined]",
    ], "combined"


def _build_overlay_filters(
    config: VideoExportConfig,
    bg_input_indices: list[int],
    current_label: str,
) -> tuple[list[str], str]:
    """Return overlay filters for each background image entry.

    Each filter composites the image over the current video stream for its
    active time window.  Returns the updated filter list and stream label.
    """
    filters: list[str] = []
    for idx, (bg, input_idx) in enumerate(
        zip(config.background_entries, bg_input_indices)
    ):
        next_label = f"bg{idx}"
        filters.append(
            f"[{current_label}][{input_idx}:v]"
            f"overlay=0:0:enable='between(t,{bg.start_time},{bg.end_time})'"
            f"[{next_label}]"
        )
        current_label = next_label
    return filters, current_label


def _build_drawtext_filters(
    config: VideoExportConfig, current_label: str
) -> tuple[list[str], str]:
    """Return ``drawtext`` filters for each subtitle entry.

    Returns the updated filter list and the final stream label.
    """
    filters: list[str] = []
    for idx, sub in enumerate(config.subtitles):
        next_label = f"sub{idx}"
        draw = (
            f"drawtext=text='{_escape_drawtext(sub.text)}'"
            f":fontsize={sub.font_size}"
            f":fontcolor={sub.color}"
            f":x={sub.x}"
            f":y={sub.y}"
            f":enable='between(t,{sub.start_time},{sub.end_time})'"
        )
        filters.append(f"[{current_label}]{draw}[{next_label}]")
        current_label = next_label
    return filters, current_label


def _build_output_args(
    config: VideoExportConfig,
    video_label: str,
    audio_input_index: Optional[int],
) -> list[str]:
    """Return the output mapping, codec, and container arguments."""
    args = ["-map", f"[{video_label}]"]
    if audio_input_index is not None:
        args += ["-map", f"{audio_input_index}:a", "-c:a", "aac", "-b:a", config.audio_bitrate]
    else:
        args += ["-an"]
    args += [
        "-t", str(config.duration),
        "-c:v", "libx264",
        "-b:v", config.video_bitrate,
        "-r", str(config.fps),
        "-pix_fmt", "yuv420p",
        config.output_path,
    ]
    return args


def build_ffmpeg_command(config: VideoExportConfig) -> list[str]:
    """Build the complete ffmpeg command list for the given export configuration.

    Constructs a ``filter_complex`` that trims, scales, and composites the two
    source videos, optionally overlays background images, burns in subtitles,
    and mixes in a VOICEVOX audio track.
    """
    cmd: list[str] = ["ffmpeg", "-y"]

    cmd += _build_video_inputs(config)

    image_args, bg_input_indices = _build_image_inputs(config, start_index=2)
    cmd += image_args

    audio_args, audio_input_index = _build_audio_input(
        config, start_index=2 + len(bg_input_indices)
    )
    cmd += audio_args

    scale_filters, current_label = _build_scale_and_layout_filters(config)
    overlay_filters, current_label = _build_overlay_filters(
        config, bg_input_indices, current_label
    )
    drawtext_filters, current_label = _build_drawtext_filters(config, current_label)

    filter_complex = ";".join(scale_filters + overlay_filters + drawtext_filters)
    cmd += ["-filter_complex", filter_complex]

    cmd += _build_output_args(config, current_label, audio_input_index)

    return cmd


def export_video(config: VideoExportConfig) -> subprocess.CompletedProcess:
    """
    Run ffmpeg to export the video described by *config*.

    Returns the CompletedProcess result. Raises subprocess.CalledProcessError
    on failure.
    """
    cmd = build_ffmpeg_command(config)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result


def probe_video(path: str) -> dict:
    """
    Return basic metadata about a video file using ffprobe.

    Returns a dict with keys: duration, width, height, fps.
    """
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration",
        "-of", "json",
        path,
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    import json

    data = json.loads(result.stdout)
    stream = data["streams"][0] if data.get("streams") else {}

    fps_str = stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/") if "/" in fps_str else (fps_str, "1")
    fps = float(num) / float(den) if float(den) != 0 else 30.0

    return {
        "duration": float(stream.get("duration", 0)),
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "fps": fps,
    }
