"""Talyhs Studio Windows desktop app. Existing web panel and workflow are untouched."""
from __future__ import annotations
import os
import sys
import subprocess
import json
import shutil
from pathlib import Path
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton, QTabWidget, QTextEdit,
    QMessageBox, QFileDialog, QTableWidget, QTableWidgetItem, QDateEdit, QSpinBox,
    QProgressBar
)
from studio.state import init_db, create_job, update_job, set_step, list_jobs, add_calendar_item, list_calendar, delete_calendar_item, record_asset
from studio.ollama import generate_script
from studio.media import master_video, align_words, make_thumbnail
from studio.publish import upload_video
from pathlib import Path

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
WORK = ROOT / "work"
VIDEO = ROOT / "youtube_short.mp4"

class JobWorker(QThread):
    log = Signal(str)
    done = Signal(bool, str, int)
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
    def run(self):
        job_id = create_job(self.settings["topic"], self.settings["language"])
        if self.settings.get("music_path"):
            from studio.state import record_asset
            record_asset(self.settings["music_path"], source="local audio",
                         creator=self.settings.get("music_creator", ""),
                         license_name=self.settings.get("music_license", ""),
                         license_url=self.settings.get("music_license_url", ""))
        env = os.environ.copy()
        env.update({
            "VIDEO_TOPIC": self.settings["topic"],
            "VIDEO_LANGUAGE": self.settings["language"],
            "TARGET_VIDEO_SECONDS": str(self.settings["duration"]),
            "VIDEO_FORMAT": self.settings["format"],
            "VOICE_GENDER": self.settings["voice"],
            "ADD_SUBTITLES": "false" if self.settings["accurate_subtitles"] else "true",
            "CREATE_THUMBNAIL": "true",
            "PUBLISH_MODE": "prepare",
            "YOUTUBE_PRIVACY_STATUS": self.settings["privacy"],
        })
        try:
            if self.settings["ollama"]:
                self.log.emit("Ollama lokal ssenarisi hazırlanır...")
                script = generate_script(self.settings["topic"], self.settings["language"],
                                         self.settings["duration"], self.settings["ollama_model"])
                WORK.mkdir(exist_ok=True)
                script_path = WORK / "script_override.txt"
                script_path.write_text(script, encoding="utf-8")
                env["SCRIPT_OVERRIDE_FILE"] = str(script_path)
                set_step(job_id, "script", "done", "Ollama local")
            set_step(job_id, "engine", "running", "youtube.py")
            if getattr(sys, "frozen", False):
                engine_exe = ROOT / "engine" / "TalyhsEngine.exe"
                if not engine_exe.exists():
                    raise RuntimeError("TalyhsEngine.exe not found in the engine folder. Rebuild using build_windows.bat.")
                command = [str(engine_exe)]
            else:
                command = [sys.executable, str(ROOT / "youtube.py")]
            proc = subprocess.Popen(command, cwd=ROOT, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", bufsize=1)
            for line in proc.stdout:
                self.log.emit(line.rstrip())
            code = proc.wait()
            if code != 0:
                raise RuntimeError(f"youtube.py exited with code {code}; see log above.")
            set_step(job_id, "engine", "done", str(VIDEO))
            if not VIDEO.exists():
                raise RuntimeError("youtube.py completed but youtube_short.mp4 was not found.")
            set_step(job_id, "mastering", "running", self.settings["audio_profile"])
            aligned_path = ""
            alignment_status = "subtitles disabled"
            if self.settings["accurate_subtitles"]:
                audio = WORK / "voiceover.mp3"
                estimated = WORK / "subtitles.ass"
                aligned_path, alignment_status = align_words(audio, WORK / "subtitles_aligned.ass",
                                                              self.settings["language"], model_name=self.settings["whisper_model"])
                if not aligned_path and estimated.exists():
                    aligned_path = str(estimated)
                self.log.emit("Subtitr rejimi: " + alignment_status)
            mastered = ROOT / "youtube_short_mastered.mp4"
            music = self.settings.get("music_path") or None
            master_video(VIDEO, mastered, WORK / "voiceover.mp3", music,
                         self.settings["audio_profile"], aligned_path or None,
                         self.settings["music_volume"])
            mastered.replace(VIDEO)
            set_step(job_id, "mastering", "done", alignment_status)
            title = self.settings["topic"][:100]
            make_thumbnail(title, WORK / "thumbnail_studio.jpg")
            set_step(job_id, "thumbnail", "done", str(WORK / "thumbnail_studio.jpg"))
            # Preserve music attribution in the metadata sent to YouTube. If the user
            # did not supply license details, clearly state that they remain unverified.
            music_path = self.settings.get("music_path", "")
            if music_path:
                metadata_file = WORK / "metadata.json"
                metadata = json.loads(metadata_file.read_text(encoding="utf-8")) if metadata_file.exists() else {
                    "title": title, "description": "", "tags": [], "language": self.settings["language"]}
                creator = self.settings.get("music_creator", "").strip()
                license_name = self.settings.get("music_license", "").strip()
                license_url = self.settings.get("music_license_url", "").strip()
                credit = f"Music attribution: {Path(music_path).name}"
                if creator:
                    credit += f" — creator: {creator}"
                if license_name and license_name != "Yükləyənin lisenziyasını yoxla":
                    credit += f" — license: {license_name}"
                else:
                    credit += " — license not verified; check rights before publishing"
                if license_url:
                    credit += f" — license/source: {license_url}"
                description = metadata.get("description", "")
                if credit not in description:
                    metadata["description"] = (description + "\n\n" + credit).strip()
                metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            update_job(job_id, "ready_for_review", str(VIDEO))
            self.done.emit(True, str(VIDEO), job_id)
        except Exception as exc:
            update_job(job_id, "failed", error=str(exc))
            set_step(job_id, "last_error", "failed", str(exc))
            self.done.emit(False, str(exc), job_id)

class PublishWorker(QThread):
    log = Signal(str)
    done = Signal(bool, str)
    def __init__(self, video_path, privacy):
        super().__init__()
        self.video_path = video_path
        self.privacy = privacy
    def run(self):
        try:
            self.log.emit("YouTube OAuth ilə video yüklənir...")
            result = upload_video(self.video_path, privacy=self.privacy,
                                  metadata_path=WORK / "metadata.json",
                                  thumbnail_path=WORK / "thumbnail_studio.jpg")
            self.done.emit(True, f"Video yükləndi: {result['url']}\nGörünmə: {result['privacy']}")
        except Exception as exc:
            self.done.emit(False, str(exc))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        self.setWindowTitle("Talyhs Studio — Windows")
        self.resize(1050, 760)
        self.worker = None
        tabs = QTabWidget()
        tabs.addTab(self._build_create_tab(), "🎬 Video hazırla")
        tabs.addTab(self._build_calendar_tab(), "🗓 Kontent təqvimi")
        tabs.addTab(self._build_history_tab(), "📂 İcra tarixçəsi")
        tabs.addTab(self._build_stats_tab(), "📊 YouTube statistikası")
        self.setCentralWidget(tabs)
    def _build_create_tab(self):
        w = QWidget(); layout = QVBoxLayout(w); form = QFormLayout()
        self.topic = QLineEdit("İnsan beyninin 5 sirri")
        self.language = QComboBox(); self.language.addItem("Azərbaycan dili", "az"); self.language.addItem("Türkçe", "tr"); self.language.addItem("English", "en")
        self.duration = QComboBox()
        for label, value in [("30 saniyə",30),("50 saniyə",50),("60 saniyə",60),("3 dəqiqə",180),("5 dəqiqə",300)]:
            self.duration.addItem(label, value)
        self.voice = QComboBox(); self.voice.addItem("Kişi səsi","male"); self.voice.addItem("Qadın səsi","female"); self.voice.addItem("Avtomatik","auto")
        self.format = QComboBox(); self.format.addItem("Shorts 9:16","vertical"); self.format.addItem("Üfüqi 16:9","horizontal")
        self.privacy = QComboBox(); self.privacy.addItem("Əvvəl yoxla (tövsiyə olunur)","private"); self.privacy.addItem("Public","public"); self.privacy.addItem("Unlisted","unlisted")
        self.audio_profile = QComboBox(); self.audio_profile.addItem("Təbii","natural"); self.audio_profile.addItem("Aydın nitq","clear_voice"); self.audio_profile.addItem("Yumşaq","soft")
        self.ollama = QCheckBox("Gemini əvəzinə lokal Ollama ilə ssenari yarat")
        self.ollama_model = QLineEdit("qwen2.5:3b")
        self.whisper = QCheckBox("Səsdən söz-söz subtitr zamanlaması (WhisperX tələb edir)")
        self.music_path = QLineEdit()
        self.music_creator = QLineEdit()
        self.music_license = QLineEdit("Yükləyənin lisenziyasını yoxla")
        self.music_license_url = QLineEdit()
        browse = QPushButton("Musiqi seç"); browse.clicked.connect(self._browse_music)
        music_row = QHBoxLayout(); music_row.addWidget(self.music_path); music_row.addWidget(browse)
        self.music_volume = QSpinBox(); self.music_volume.setRange(0,25); self.music_volume.setValue(10); self.music_volume.setSuffix("%")
        form.addRow("Video mövzusu", self.topic); form.addRow("Dil", self.language)
        form.addRow("Müddət", self.duration); form.addRow("Səs", self.voice); form.addRow("Format", self.format)
        form.addRow("Yayımlama", self.privacy); form.addRow("Audio profili", self.audio_profile)
        form.addRow("", self.ollama); form.addRow("Ollama modeli", self.ollama_model); form.addRow("", self.whisper)
        form.addRow("Fon musiqisi", music_row)
        form.addRow("Musiqi müəllifi", self.music_creator)
        form.addRow("Lisenziya", self.music_license)
        form.addRow("Lisenziya URL-si", self.music_license_url)
        form.addRow("Musiqi səviyyəsi", self.music_volume)
        layout.addLayout(form)
        self.progress = QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.generate_btn = QPushButton("▶ Video hazırla (yalnız baxış üçün)"); self.generate_btn.clicked.connect(self._generate)
        self.preview_btn = QPushButton("Videoya bax"); self.preview_btn.clicked.connect(self._preview); self.preview_btn.setEnabled(VIDEO.exists())
        self.publish_btn = QPushButton("YouTube-a yüklə"); self.publish_btn.clicked.connect(self._publish); self.publish_btn.setEnabled(False)
        buttons.addWidget(self.generate_btn); buttons.addWidget(self.preview_btn); buttons.addWidget(self.publish_btn)
        layout.addLayout(buttons)
        self.log = QTextEdit(); self.log.setReadOnly(True); layout.addWidget(self.log, 1)
        layout.addWidget(QLabel("Təhlükəsizlik: bu proqram videonu əvvəlcə lokal hazırlayır. Public yükləmə ayrıca təsdiq tələb edir."))
        return w
    def _browse_music(self):
        path, _ = QFileDialog.getOpenFileName(self, "Fon musiqisi seç", "", "Audio (*.mp3 *.wav *.m4a *.flac)")
        if path:
            self.music_path.setText(path)
            self.log.append("Musiqi seçildi. Lisenziyanı yoxla və məlumatlarını doldur.")
    def _generate(self):
        if not self.topic.text().strip():
            QMessageBox.warning(self, "Mövzu lazımdır", "Video mövzusunu daxil et."); return
        settings = {"topic": self.topic.text().strip(), "language": self.language.currentData(),
                    "duration": self.duration.currentData(), "voice": self.voice.currentData(),
                    "format": self.format.currentData(), "privacy": self.privacy.currentData(),
                    "audio_profile": self.audio_profile.currentData(), "accurate_subtitles": self.whisper.isChecked(),
                    "ollama": self.ollama.isChecked(), "ollama_model": self.ollama_model.text().strip() or "qwen2.5:3b",
                    "music_path": self.music_path.text().strip(), "music_volume": self.music_volume.value()/100,
                    "music_creator": self.music_creator.text().strip(),
                    "music_license": self.music_license.text().strip(),
                    "music_license_url": self.music_license_url.text().strip(),
                    "whisper_model": "small"}
        self.generate_btn.setEnabled(False); self.publish_btn.setEnabled(False); self.progress.show(); self.log.clear()
        self.worker = JobWorker(settings); self.worker.log.connect(self.log.append); self.worker.done.connect(self._job_done); self.worker.start()
    def _job_done(self, ok, message, job_id):
        self.progress.hide(); self.generate_btn.setEnabled(True); self.preview_btn.setEnabled(VIDEO.exists()); self._refresh_history()
        if ok:
            self.log.append(f"İş #{job_id} hazırdır: {message}")
            self.publish_btn.setEnabled(True)
            QMessageBox.information(self, "Hazırdır", "Video hazırdır. Baxışdan keçir və sonra yayımla.")
        else:
            self.log.append("XƏTA: " + message)
            QMessageBox.critical(self, "Video hazırlamaq alınmadı", message)
    def _preview(self):
        if VIDEO.exists():
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(VIDEO)))
        else: QMessageBox.information(self, "Video yoxdur", "Əvvəl video hazırla.")
    def _publish(self):
        if not VIDEO.exists():
            QMessageBox.warning(self, "Video yoxdur", "Əvvəlcə video hazırla.")
            return
        privacy = getattr(self, "last_settings", {}).get("privacy", "private")
        prompt = "Videonu YouTube-a yükləmək istəyirsən? Görünmə: " + privacy.upper()
        if privacy == "public":
            prompt += "\n\nDiqqət: video hamıya açıq olacaq."
        answer = QMessageBox.question(self, "YouTube-a yüklə", prompt,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.publish_btn.setEnabled(False)
        self.progress.show()
        self.publish_worker = PublishWorker(str(VIDEO), privacy)
        self.publish_worker.log.connect(self.log.append)
        self.publish_worker.done.connect(self._publish_done)
        self.publish_worker.start()
    def _publish_done(self, ok, message):
        self.progress.hide()
        self.publish_btn.setEnabled(VIDEO.exists())
        if ok:
            QMessageBox.information(self, "Yükləmə tamamlandı", message)
            self.log.append(message)
        else:
            QMessageBox.critical(self, "YouTube yükləmə xətası", message)
            self.log.append("YÜKLƏMƏ XƏTASI: " + message)
    def _build_calendar_tab(self):
        w=QWidget(); layout=QVBoxLayout(w); form=QFormLayout()
        self.cal_topic=QLineEdit(); self.cal_language=QComboBox()
        for label,code in [("Azərbaycan dili","az"),("Türkçe","tr"),("English","en")]: self.cal_language.addItem(label,code)
        self.cal_date=QDateEdit(); self.cal_date.setCalendarPopup(True); self.cal_date.setDate(self.cal_date.date().currentDate())
        self.cal_notes=QLineEdit()
        form.addRow("Mövzu",self.cal_topic); form.addRow("Dil",self.cal_language); form.addRow("Tarix",self.cal_date); form.addRow("Qeyd",self.cal_notes)
        layout.addLayout(form)
        add=QPushButton("Təqvimə əlavə et"); add.clicked.connect(self._add_calendar); layout.addWidget(add)
        self.calendar_table=QTableWidget(0,5); self.calendar_table.setHorizontalHeaderLabels(["ID","Mövzu","Dil","Tarix","Status"]); layout.addWidget(self.calendar_table)
        refresh=QPushButton("Yenilə"); refresh.clicked.connect(self._refresh_calendar); layout.addWidget(refresh)
        self._refresh_calendar(); return w
    def _add_calendar(self):
        if not self.cal_topic.text().strip(): return
        add_calendar_item(self.cal_topic.text().strip(),self.cal_language.currentData(),self.cal_date.date().toString("yyyy-MM-dd"),self.cal_notes.text())
        self._refresh_calendar()
    def _refresh_calendar(self):
        if not hasattr(self,"calendar_table"): return
        rows=list_calendar(); self.calendar_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,val in enumerate([r["id"],r["topic"],r["language"],r["planned_date"] or "",r["status"]]):
                self.calendar_table.setItem(i,j,QTableWidgetItem(str(val)))
    def _build_history_tab(self):
        w=QWidget(); layout=QVBoxLayout(w); self.history_table=QTableWidget(0,5)
        self.history_table.setHorizontalHeaderLabels(["ID","Mövzu","Dil","Status","Fayl / Xəta"])
        layout.addWidget(self.history_table); btn=QPushButton("Tarixçəni yenilə"); btn.clicked.connect(self._refresh_history); layout.addWidget(btn)
        self._refresh_history(); return w
    def _refresh_history(self):
        rows=list_jobs(); self.history_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,val in enumerate([r["id"],r["topic"],r["language"],r["status"],r["output_path"] or r["error"] or ""]):
                self.history_table.setItem(i,j,QTableWidgetItem(str(val)))
    def _build_stats_tab(self):
        w=QWidget(); layout=QVBoxLayout(w)
        self.stats_text=QTextEdit(); self.stats_text.setReadOnly(True); layout.addWidget(self.stats_text)
        btn=QPushButton("YouTube statistikasını yüklə"); btn.clicked.connect(self._load_stats); layout.addWidget(btn)
        self.stats_text.setPlainText("Statistika üçün lokal token.json və ya TOKEN_JSON mühit dəyişəni, həmçinin YouTube Data API icazəsi tələb olunur.")
        return w
    def _load_stats(self):
        try:
            from studio.stats import channel_summary, recent_videos
            summary=channel_summary(); videos=recent_videos()
            text=(f"Kanal: {summary['title']}\nBaxışlar: {summary['views']:,}\nAbunəçilər: {summary['subscribers']:,}\nVideolar: {summary['videos']:,}\n\nSon videolar:\n")
            for v in videos: text += f"• {v['title']} — {v['views']:,} baxış, {v['likes']:,} bəyənmə\n"
            self.stats_text.setPlainText(text)
        except Exception as exc:
            self.stats_text.setPlainText(f"Statistika yüklənmədi: {exc}")

def main():
    app=QApplication(sys.argv)
    window=MainWindow(); window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
