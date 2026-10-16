"""Free post-render quality checks and thumbnail generation for fitness Shorts."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def run_probe(path: str | Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration,size:stream=codec_type,width,height",
            "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return json.loads(result.stdout)


def validate_video(path: str | Path, expected_seconds: int = 45) -> dict:
    """Validate the rendered MP4 before it is offered for review or upload."""
    path = Path(path)
    issues: list[str] = []
    warnings: list[str] = []
    if not path.exists() or path.stat().st_size < 50_000:
        return {"ok": False, "issues": ["Video file is missing or unexpectedly small."], "warnings": []}
    try:
        info = run_probe(path)
        streams = info.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        duration = float(info.get("format", {}).get("duration", 0))
        if not video:
            issues.append("No video stream found.")
        else:
            if int(video.get("width", 0)) != 1080 or int(video.get("height", 0)) != 1920:
                issues.append("Video is not 1080x1920 vertical format.")
        if not audio:
            issues.append("No audio stream found.")
        if duration < 25 or duration > expected_seconds + 2:
            issues.append(f"Unexpected duration: {duration:.1f}s.")
        if duration < expected_seconds - 3:
            warnings.append(f"Rendered video is shorter than target ({duration:.1f}s vs {expected_seconds}s).")
        return {
            "ok": not issues,
            "duration_seconds": round(duration, 2),
            "size_bytes": path.stat().st_size,
            "resolution": f"{video.get('width')}x{video.get('height')}" if video else None,
            "has_audio": audio is not None,
            "issues": issues,
            "warnings": warnings,
        }
    except Exception as exc:
        return {"ok": False, "issues": [f"Could not inspect video: {exc}"], "warnings": []}


def create_thumbnail(video_path: str | Path, title: str, output_path: str | Path) -> Path:
    """Extract a frame and create a readable 1280x720 title card with Pillow."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    video_path, output_path = Path(video_path), Path(output_path)
    frame = output_path.with_suffix(".frame.jpg")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(video_path),
         "-frames:v", "1", "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
         str(frame)],
        check=True, capture_output=True, timeout=60,
    )
    try:
        image = Image.open(frame).convert("RGB")
        overlay = Image.new("RGBA", image.size, (4, 12, 24, 105))
        image = Image.alpha_composite(image.convert("RGBA"), overlay)
        draw = ImageDraw.Draw(image)
        fonts = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
        font_path = next((p for p in fonts if Path(p).exists()), None)
        font = ImageFont.truetype(font_path, 66) if font_path else ImageFont.load_default()
        words = re.sub(r"\s+", " ", title).strip().upper().split()
        lines, current = [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textbbox((0, 0), candidate, font=font)[2] <= 1120:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        lines = lines[:3]
        y = max(130, (720 - len(lines) * 82) // 2)
        draw.rounded_rectangle((55, y - 35, 1225, y + len(lines) * 82 + 25),
                               radius=28, fill=(3, 15, 28, 205), outline=(35, 230, 185, 235), width=4)
        for line in lines:
            draw.text((85, y + 3), line, font=font, fill=(0, 0, 0, 255), stroke_width=2)
            draw.text((80, y), line, font=font, fill=(255, 255, 255, 255),
                      stroke_width=1, stroke_fill=(5, 18, 30, 255))
            y += 82
        draw.rounded_rectangle((55, 610, 430, 666), radius=16, fill=(35, 230, 185, 255))
        small = ImageFont.truetype(font_path, 25) if font_path else ImageFont.load_default()
        draw.text((78, 624), "FITNESS • FORM • CONSISTENCY", font=small, fill=(3, 22, 32, 255))
        image.convert("RGB").save(output_path, "JPEG", quality=92, optimize=True)
    finally:
        frame.unlink(missing_ok=True)
    return output_path


def write_review_manifest(output_dir: str | Path, title: str, video_path: str | Path,
                          thumbnail_path: str | Path, quality: dict, credits: list[str]) -> Path:
    output_dir = Path(output_dir)
    manifest = {
        "title": title,
        "video": Path(video_path).name,
        "thumbnail": Path(thumbnail_path).name,
        "quality_check": quality,
        "stock_credits": credits,
        "status": "READY_FOR_HUMAN_REVIEW" if quality.get("ok") else "FAILED_QUALITY_CHECK",
        "publish_authorized": False,
        "note": "Review the video, narration, captions, footage relevance and fitness claims before choosing upload mode.",
    }
    path = output_dir / "review_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
