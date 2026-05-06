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
    """Escape special characters for the ffmpeg drawtext filter."""
    # Order matters: backslash first
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    return text


def build_ffmpeg_command(config: VideoExportConfig) -> list[str]:
    """
    Build the ffmpeg command list for the given export configuration.

    The function constructs a filter_complex that:
    1. Trims each video to the requested start offset.
    2. Scales each video to fill its half of the output canvas.
    3. Places both clips side-by-side (or top/bottom).
    4. Overlays any background images.
    5. Draws subtitle text for each SubtitleEntry.
    6. Mixes in the optional VOICEVOX audio track.
    """
    cmd: list[str] = ["ffmpeg", "-y"]

    # ---- Inputs ----
    # Input 0: video 1
    cmd += ["-ss", str(config.video1_start), "-i", config.video1_path]
    # Input 1: video 2
    cmd += ["-ss", str(config.video2_start), "-i", config.video2_path]

    input_count = 2

    background_input_indices: list[int] = []
    for bg in config.background_entries:
        cmd += ["-i", bg.image_path]
        background_input_indices.append(input_count)
        input_count += 1

    audio_input_index: Optional[int] = None
    if config.audio_path:
        cmd += [
            "-ss",
            str(config.audio_start),
            "-i",
            config.audio_path,
        ]
        audio_input_index = input_count
        input_count += 1

    # ---- filter_complex ----
    w = config.output_width
    h = config.output_height

    if config.layout == "side_by_side":
        half_w = w // 2
        scale_w, scale_h = half_w, h
    else:  # top_bottom
        half_h = h // 2
        scale_w, scale_h = w, half_h

    filters: list[str] = []

    # Scale each clip
    filters.append(
        f"[0:v]scale={scale_w}:{scale_h}:force_original_aspect_ratio=decrease,"
        f"pad={scale_w}:{scale_h}:(ow-iw)/2:(oh-ih)/2[v0]"
    )
    filters.append(
        f"[1:v]scale={scale_w}:{scale_h}:force_original_aspect_ratio=decrease,"
        f"pad={scale_w}:{scale_h}:(ow-iw)/2:(oh-ih)/2[v1]"
    )

    # Combine clips
    if config.layout == "side_by_side":
        filters.append(f"[v0][v1]hstack=inputs=2[combined]")
    else:
        filters.append(f"[v0][v1]vstack=inputs=2[combined]")

    current_label = "combined"

    # Overlay background images
    for idx, (bg, bg_input_idx) in enumerate(
        zip(config.background_entries, background_input_indices)
    ):
        next_label = f"bg{idx}"
        filters.append(
            f"[{current_label}][{bg_input_idx}:v]"
            f"overlay=0:0:enable='between(t,{bg.start_time},{bg.end_time})'[{next_label}]"
        )
        current_label = next_label

    # Draw subtitles
    for idx, sub in enumerate(config.subtitles):
        next_label = f"sub{idx}"
        escaped = _escape_drawtext(sub.text)
        draw = (
            f"drawtext=text='{escaped}'"
            f":fontsize={sub.font_size}"
            f":fontcolor={sub.color}"
            f":x={sub.x}"
            f":y={sub.y}"
            f":enable='between(t,{sub.start_time},{sub.end_time})'"
        )
        filters.append(f"[{current_label}]{draw}[{next_label}]")
        current_label = next_label

    filter_complex = ";".join(filters)

    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", f"[{current_label}]"]

    # Audio mapping
    if audio_input_index is not None:
        cmd += ["-map", f"{audio_input_index}:a"]
        cmd += ["-c:a", "aac", "-b:a", config.audio_bitrate]
    else:
        cmd += ["-an"]

    # Output settings
    cmd += [
        "-t", str(config.duration),
        "-c:v", "libx264",
        "-b:v", config.video_bitrate,
        "-r", str(config.fps),
        "-pix_fmt", "yuv420p",
        config.output_path,
    ]

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
