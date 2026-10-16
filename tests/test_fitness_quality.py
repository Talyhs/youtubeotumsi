from youtube_fitnes_talyhs import quality


def test_validate_video_accepts_vertical_video_with_audio(tmp_path, monkeypatch):
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"x" * 60000)
    monkeypatch.setattr(
        quality,
        "run_probe",
        lambda _path: {
            "format": {"duration": "45.0", "size": "60000"},
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920},
                {"codec_type": "audio"},
            ],
        },
    )
    result = quality.validate_video(video, expected_seconds=45)
    assert result["ok"] is True
    assert result["resolution"] == "1080x1920"
    assert result["has_audio"] is True
    assert result["issues"] == []


def test_validate_video_rejects_missing_audio(tmp_path, monkeypatch):
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"x" * 60000)
    monkeypatch.setattr(
        quality,
        "run_probe",
        lambda _path: {
            "format": {"duration": "45.0", "size": "60000"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}],
        },
    )
    result = quality.validate_video(video, expected_seconds=45)
    assert result["ok"] is False
    assert "No audio stream found." in result["issues"]


def test_review_manifest_starts_unapproved(tmp_path):
    manifest = quality.write_review_manifest(
        tmp_path, "Push-up form", tmp_path / "fitness_shorts.mp4",
        tmp_path / "thumbnail.jpg", {"ok": True, "issues": [], "warnings": []},
        ["- Pexels creator: https://example.com/video"],
    )
    import json
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["status"] == "READY_FOR_HUMAN_REVIEW"
    assert payload["publish_authorized"] is False
