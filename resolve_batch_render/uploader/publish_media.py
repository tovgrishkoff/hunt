"""Feed video profile for Instagram, YouTube and Pinterest.

Resolve exports are HEVC inside a QuickTime file, often with a timecode
track and no audio. Those three platforms get one H.264 MP4 instead.
Telegram Stories keep their own 720x1280 file at publish time.
"""

from __future__ import annotations

import fcntl
import os
import socket
import struct
import subprocess
import time
import uuid
from pathlib import Path

from loguru import logger

from uploader.media_file import incomplete_reason
from uploader.telegram_stories_publisher import _mp4_info

ROOT = Path(__file__).resolve().parent.parent
FEED_DIR = ROOT / "output" / "publish_ready"

# Shared volume is mounted into every autopost container. Main process is PID 1
# in each of them, so a temp name based only on os.getpid() collides and two
# ffmpeg jobs write the same file (and one finally-block deletes the other).


def _moov_before_mdat(path: Path) -> bool:
    """True when the index sits before the media data (faststart)."""
    moov_at = -1
    mdat_at = -1
    try:
        end = path.stat().st_size
        with path.open("rb") as handle:
            while handle.tell() + 8 <= end:
                pos = handle.tell()
                hdr = handle.read(8)
                if len(hdr) < 8:
                    break
                size, typ_b = struct.unpack(">I4s", hdr)
                hdr_len = 8
                if size == 1:
                    ext = handle.read(8)
                    if len(ext) < 8:
                        break
                    size = struct.unpack(">Q", ext)[0]
                    hdr_len = 16
                elif size == 0:
                    size = end - pos
                if size < hdr_len or pos + size > end:
                    break
                typ = typ_b.decode("latin1", errors="replace")
                if typ == "moov" and moov_at < 0:
                    moov_at = pos
                if typ == "mdat" and mdat_at < 0:
                    mdat_at = pos
                if moov_at >= 0 and mdat_at >= 0:
                    break
                handle.seek(pos + size)
    except OSError:
        return False
    return moov_at >= 0 and (mdat_at < 0 or moov_at < mdat_at)


def feed_mismatch(path: Path) -> str:
    """Why this file is not ready for Instagram, YouTube and Pinterest."""
    reason = incomplete_reason(path)
    if reason:
        return reason
    if path.suffix.lower() != ".mp4":
        return "container is not mp4"
    info = _mp4_info(path)
    if info["vcodec"] != "h264":
        return f"video {info['vcodec'] or 'unknown'}, need h264"
    if info["width"] != 1080 or info["height"] != 1920:
        return f"frame {info['width']}x{info['height']}, need 1080x1920"
    if not info["has_audio"] or info["acodec"] != "aac":
        return "audio is not aac stereo"
    if info["has_tmcd"]:
        return "timecode track"
    if info["duration_sec"] and info["duration_sec"] < 3:
        return f"duration {info['duration_sec']}s, Instagram minimum is 3s"
    if not _moov_before_mdat(path):
        return "moov atom is after mdat"
    return ""


def _feed_ready(path: Path, *, src_mtime: float) -> bool:
    return (
        path.is_file()
        and path.stat().st_size > 10_000
        and path.stat().st_mtime >= src_mtime
        and not feed_mismatch(path)
    )


def _unique_tmp(stem: str) -> Path:
    host = socket.gethostname().replace("/", "_")[:12] or "host"
    token = uuid.uuid4().hex[:8]
    return FEED_DIR / f".{stem}.{host}.{os.getpid()}.{token}.mp4"


def _feed_vf(info: dict) -> str:
    """Build a cheap filter graph. Skip scale/pad/fps when the frame is already 9:16."""
    parts: list[str] = []
    if info.get("width") != 1080 or info.get("height") != 1920:
        parts.append(
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    parts.append("setsar=1")
    # Keep source fps (Resolve hotel reels are usually 25). Forcing 30 adds
    # interpolation work and made 10-bit HEVC encodes miss the 1200s budget.
    return ",".join(parts)


def _transcode_timeout_sec(info: dict) -> int:
    """Give heavy 10-bit HEVC sources room without hanging forever."""
    dur = max(1, int(info.get("duration_sec") or 60))
    # ~45s wall per second of source under one thread + headroom.
    return max(1200, min(3600, dur * 45 + 300))


def _run_ffmpeg(cmd: list[str], *, timeout: int) -> None:
    try:
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = (exc.stderr or b"")[-4000:].decode("utf-8", errors="replace")
        logger.error(f"[media] ffmpeg timed out after {timeout}s: {stderr[-1500:]}")
        raise
    if completed.returncode != 0:
        stderr = (completed.stderr or b"")[-4000:].decode("utf-8", errors="replace")
        logger.error(
            f"[media] ffmpeg exit {completed.returncode}: {stderr[-1500:]}"
        )
        raise subprocess.CalledProcessError(
            completed.returncode, cmd, output=completed.stdout, stderr=completed.stderr
        )


def _encode_feed_mp4(src: Path, out: Path, *, stem: str) -> None:
    info = _mp4_info(src)
    tmp = _unique_tmp(stem)
    vf = _feed_vf(info)
    # One decode/encode thread: 10-bit HEVC at ~50 Mbps SIGKILLs under the
    # shared 512–768m cgroup when two containers race with -threads 2.
    cmd = ["ffmpeg", "-y", "-threads", "1", "-i", str(src)]
    if info["has_audio"]:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
    else:
        logger.warning(
            f"[media] {src.name} has no audio track; feed file will be silent"
        )
        cmd += [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
        ]
    cmd += [
        "-dn",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-x264-params",
        "threads=1:rc-lookahead=10:ref=1",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-map_metadata",
        "-1",
        "-write_tmcd",
        "0",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    reason = feed_mismatch(src) or "refresh"
    timeout = _transcode_timeout_sec(info)
    logger.info(
        f"[media] feed transcode {src.name} → {out.name} ({reason}) "
        f"tmp={tmp.name} timeout={timeout}s vf={vf}"
    )
    try:
        _run_ffmpeg(cmd, timeout=timeout)
        if not tmp.is_file() or tmp.stat().st_size < 1000 or feed_mismatch(tmp):
            raise RuntimeError(
                f"feed transcode failed for {src.name}: "
                f"{feed_mismatch(tmp) if tmp.is_file() else 'empty'}"
            )
        os.replace(tmp, out)
    finally:
        if tmp.is_file():
            try:
                tmp.unlink()
            except OSError:
                pass


def ensure_feed_mp4(video_path: Path, *, reel_id: str = "") -> Path:
    """Return a cached H.264 1080x1920 MP4. Re-encodes only when needed."""
    src = Path(video_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))

    FEED_DIR.mkdir(parents=True, exist_ok=True)
    stem = (reel_id or src.stem).replace("/", "_").replace(" ", "_")
    out = FEED_DIR / f"{stem}.mp4"
    src_mtime = src.stat().st_mtime

    if _feed_ready(out, src_mtime=src_mtime):
        return out
    if src.resolve() != out.resolve() and not feed_mismatch(src):
        return src

    lock_path = FEED_DIR / f".{stem}.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_fh:
        logger.info(f"[media] waiting for feed lock {lock_path.name}")
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            # Another container may have finished while we waited.
            if _feed_ready(out, src_mtime=src_mtime):
                logger.info(f"[media] feed ready after wait {out.name}")
                return out
            if src.resolve() != out.resolve() and not feed_mismatch(src):
                return src
            lock_fh.seek(0)
            lock_fh.truncate()
            lock_fh.write(f"{socket.gethostname()} {os.getpid()} {time.time():.0f}\n")
            lock_fh.flush()
            _encode_feed_mp4(src, out, stem=stem)
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)

    logger.info(f"[media] feed ready {out.name} {out.stat().st_size // (1024 * 1024)}MB")
    return out
