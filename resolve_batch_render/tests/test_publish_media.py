"""Unit tests for feed MP4 prep (no ffmpeg encode)."""

from __future__ import annotations

from pathlib import Path

from uploader.publish_media import _feed_vf, _transcode_timeout_sec, _unique_tmp


def test_feed_vf_skips_scale_when_already_vertical() -> None:
    assert _feed_vf({"width": 1080, "height": 1920}) == "setsar=1"


def test_feed_vf_scales_when_needed() -> None:
    vf = _feed_vf({"width": 1920, "height": 1080})
    assert "scale=1080:1920" in vf
    assert "pad=1080:1920" in vf
    assert vf.endswith("setsar=1")


def test_transcode_timeout_scales_with_duration() -> None:
    assert _transcode_timeout_sec({"duration_sec": 10}) == 1200
    assert _transcode_timeout_sec({"duration_sec": 37}) >= 1200
    assert _transcode_timeout_sec({"duration_sec": 120}) == 3600


def test_unique_tmp_uses_host_and_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("uploader.publish_media.FEED_DIR", tmp_path)
    monkeypatch.setattr("uploader.publish_media.socket.gethostname", lambda: "box/a")
    a = _unique_tmp("CRUISE__POOL")
    b = _unique_tmp("CRUISE__POOL")
    assert a.name.startswith(".CRUISE__POOL.box_a.")
    assert a != b
    assert a.suffix == ".mp4"
