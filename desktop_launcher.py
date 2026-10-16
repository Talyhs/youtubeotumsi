from __future__ import annotations
import json
import os
import sys
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog

APP_NAME = "Talyhs YouTube Studio"
DEFAULT_URL = os.environ.get("TALYHS_STUDIO_URL", "").strip()
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "TalyhsStudio"
CONFIG_FILE = CONFIG_DIR / "launcher.json"

def read_url() -> str:
    try:
        value = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("url", "")
        return value if isinstance(value, str) else ""
    except Exception:
        return DEFAULT_URL

def write_url(value: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"url": value}, ensure_ascii=False, indent=2), encoding="utf-8")

def valid_url(value: str) -> bool:
    return value.startswith("https://") and "." in value.split("://", 1)[1] and " " not in value

def self_test() -> int:
    assert APP_NAME
    assert valid_url("https://example.onrender.com")
    assert not valid_url("http://example.com")
    assert not valid_url("not-a-url")
    return 0

def main() -> None:
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("720x460")
    root.minsize(620, 400)
    root.configure(bg="#0b1020")
    current = read_url()

    title = tk.Label(root, text="TALYHS  /  YOUTUBE STUDIO", font=("Segoe UI", 20, "bold"),
                     fg="#f3f6ff", bg="#0b1020")
    title.pack(anchor="w", padx=28, pady=(28, 4))
    subtitle = tk.Label(root, text="Video automation command center", font=("Segoe UI", 10),
                        fg="#9eacc8", bg="#0b1020")
    subtitle.pack(anchor="w", padx=30, pady=(0, 24))

    card = tk.Frame(root, bg="#121b2e", highlightbackground="#293752", highlightthickness=1)
    card.pack(fill="x", padx=28, pady=4)
    tk.Label(card, text="WEB STUDIO URL", font=("Segoe UI", 9, "bold"), fg="#aab8d4",
             bg="#121b2e").pack(anchor="w", padx=16, pady=(16, 6))
    url_var = tk.StringVar(value=current)
    entry = tk.Entry(card, textvariable=url_var, font=("Segoe UI", 11), bg="#0b1020",
                     fg="#f3f6ff", insertbackground="#ffffff", relief="flat")
    entry.pack(fill="x", padx=16, ipady=10)
    hint = tk.Label(card, text="Paste your deployed Render panel URL (must start with https://).",
                    font=("Segoe UI", 9), fg="#9eacc8", bg="#121b2e")
    hint.pack(anchor="w", padx=16, pady=(8, 16))

    def save() -> str:
        value = url_var.get().strip().rstrip("/")
        if not valid_url(value):
            messagebox.showerror(APP_NAME, "Düzgün HTTPS Render panel linkini daxil et.\nMəsələn: https://your-service.onrender.com")
            return ""
        write_url(value)
        return value

    def open_panel() -> None:
        value = save()
        if value:
            webbrowser.open(value)

    buttons = tk.Frame(root, bg="#0b1020")
    buttons.pack(fill="x", padx=28, pady=18)
    tk.Button(buttons, text="PANELİ AÇ", command=open_panel, bg="#6d5dfc", fg="white",
              activebackground="#8276ff", activeforeground="white", relief="flat",
              font=("Segoe UI", 10, "bold"), padx=20, pady=12).pack(side="left")
    tk.Button(buttons, text="LINKİ YADDA SAXLA", command=lambda: messagebox.showinfo(APP_NAME, "Link yadda saxlanıldı.") if save() else None,
              bg="#202c44", fg="#f3f6ff", activebackground="#2d3b58", relief="flat",
              font=("Segoe UI", 10), padx=16, pady=12).pack(side="left", padx=10)

    footer = tk.Label(root, text="Bu EXE veb panelə giriş üçün masaüstü başladıcıdır; panelin internet bağlantısı və Render konfiqurasiyası tələb olunur.",
                      wraplength=650, justify="left", font=("Segoe UI", 9), fg="#9eacc8", bg="#0b1020")
    footer.pack(anchor="w", padx=30, side="bottom", pady=20)
    root.mainloop()

if __name__ == "__main__":
    main()
