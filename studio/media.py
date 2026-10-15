"""Local audio mastering, optional word alignment, subtitles and thumbnails."""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def run_checked(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Command failed: {command[0]}\n{result.stderr[-2500:]}")
    return result.stdout

def ffmpeg_available():
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

AUDIO_PROFILES = {
    "natural": "highpass=f=70,lowpass=f=15000,acompressor=threshold=0.125:ratio=2.2:attack=15:release=180,loudnorm=I=-16:TP=-1.5:LRA=11",
    "clear_voice": "highpass=f=85,equalizer=f=250:t=q:w=1:g=-2,equalizer=f=3200:t=q:w=1:g=2,acompressor=threshold=0.10:ratio=2.8:attack=10:release=160,loudnorm=I=-16:TP=-1.5:LRA=9",
    "soft": "highpass=f=65,lowpass=f=13000,acompressor=threshold=0.14:ratio=1.8:attack=20:release=220,loudnorm=I=-18:TP=-2:LRA=12",
}

def escape_filter_path(path):
    return str(Path(path).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")

def align_words(audio_path, output_ass, language="az", device="cpu", model_name="small"):
    """Try WhisperX word alignment; returns (path, mode). Falls back to existing estimated ASS."""
    audio_path, output_ass = Path(audio_path), Path(output_ass)
    try:
        import whisperx
        import torch
        actual_device = "cuda" if device == "cuda" and torch.cuda.is_available() else "cpu"
        compute_type = "float16" if actual_device == "cuda" else "int8"
        model = whisperx.load_model(model_name, actual_device, compute_type=compute_type, language=language)
        audio = whisperx.load_audio(str(audio_path))
        result = model.transcribe(audio, batch_size=4, language=language)
        align_model, metadata = whisperx.load_align_model(language_code=language, device=actual_device)
        aligned = whisperx.align(result["segments"], align_model, metadata, audio, actual_device,
                                 return_char_alignments=False)
        words = aligned.get("word_segments") or []
        if not words:
            raise RuntimeError("WhisperX did not return word-level timestamps for this language/model.")
        lines = [
            "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
            "ScaledBorderAndShadow: yes", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,Arial,62,&H00FFFFFF,&H0000FFFF,&H00101010,&H80000000,-1,0,1,4,1,2,70,70,190,1", "",
            "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]
        def stamp(value):
            centis = max(0, int(float(value) * 100))
            h, rem = divmod(centis, 360000)
            m, rem = divmod(rem, 6000)
            s, cs = divmod(rem, 100)
            return f"{h}:{m:02}:{s:02}.{cs:02}"
        for word in words:
            token = str(word.get("word", "")).strip()
            if not token:
                continue
            start = max(0, float(word.get("start", 0)))
            end = max(start + 0.08, float(word.get("end", start + 0.15)))
            token = token.replace("{", r"\{").replace("}", r"\}")
            lines.append(f"Dialogue: 0,{stamp(start)},{stamp(end)},Default,,0,0,0,,{token}")
        output_ass.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(output_ass), "whisperx_word_alignment"
    except Exception as exc:
        return "", f"fallback_estimated_subtitles: {exc}"

def make_thumbnail(title, output_path, background_path=None, width=1280, height=720):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if background_path and Path(background_path).exists():
        image = Image.open(background_path).convert("RGB").resize((width, height))
    else:
        image = Image.new("RGB", (width, height), (13, 24, 45))
        pixels = image.load()
        for y in range(height):
            for x in range(width):
                blend = int(18 + 28 * x / width + 12 * y / height)
                pixels[x, y] = (10, min(70, blend), min(110, blend + 20))
    draw = ImageDraw.Draw(image)
    try:
        font_path = "C:/Windows/Fonts/arialbd.ttf"
        font = ImageFont.truetype(font_path, 68)
    except OSError:
        font = ImageFont.load_default()
    words = title.strip()[:95].split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] > width - 120 and current:
            lines.append(current); current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    text = "\n".join(lines[:3])
    draw.rounded_rectangle((38, height-300, width-38, height-45), radius=28, fill=(5, 12, 25))
    draw.multiline_text((65, height-270), text, font=font, fill=(255,255,255), spacing=12,
                        stroke_width=2, stroke_fill=(0,0,0))
    image.save(output_path, quality=92)
    return str(output_path)

def master_video(input_video, output_video, voice_path=None, music_path=None, profile="natural", subtitles_path=None, music_volume=0.10):
    """Remux video with mastered narration and optional background music/subtitles."""
    if not ffmpeg_available():
        raise RuntimeError("FFmpeg/ffprobe not found. Install FFmpeg and add its bin folder to PATH.")
    input_video, output_video = Path(input_video), Path(output_video)
    output_video.parent.mkdir(parents=True, exist_ok=True)
    filters = AUDIO_PROFILES.get(profile, AUDIO_PROFILES["natural"])
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_video)]
    voice_index = None
    music_index = None
    if voice_path and Path(voice_path).exists():
        cmd += ["-i", str(voice_path)]
        voice_index = 1
    if music_path and Path(music_path).exists():
        cmd += ["-i", str(music_path)]
        music_index = 2 if voice_index is not None else 1
    video_filter = f"subtitles='{escape_filter_path(subtitles_path)}'" if subtitles_path and Path(subtitles_path).exists() else "null"
    graph = []
    if voice_index is not None:
        graph.append(f"[{voice_index}:a]{filters}[voice]")
    else:
        graph.append(f"[0:a]{filters}[voice]")
    if music_index is not None:
        graph.append(f"[{music_index}:a]volume={max(0.0,min(0.25,float(music_volume))):.3f},afade=t=in:st=0:d=1.0[music]")
        graph.append("[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]")
    else:
        graph.append("[voice]anull[aout]")
    cmd += ["-vf", video_filter, "-filter_complex", ";".join(graph),
            "-map", "0:v:0", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "21", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output_video)]
    run_checked(cmd)
    if not output_video.exists() or output_video.stat().st_size < 100_000:
        raise RuntimeError("Mastered video was not created or is unexpectedly small.")
    return str(output_video)
