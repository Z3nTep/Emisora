import os
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.music_scanner import scan_music
from shared.config_handler import load_config, save_config, get_weighted_category

# --- Colores ---
BG_COLOR = "#0f172a"
PANEL_BG = "#1e293b"
TEXT_MAIN = "#f8fafc"
TEXT_MUTED = "#94a3b8"
ACCENT = "#c084fc"
ACCENT_DIM = "#7c3aed"
GREEN = "#4ade80"

class PlayerUI:
    def __init__(self, obs_controller, widget_updater, music_dir, auto_play, config_path):
        self.root = tk.Tk()
        self.root.title("Auto Media Player")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("480x650")
        self.root.minsize(400, 500)

        self.obs = obs_controller
        self.widget = widget_updater
        self.music_dir = music_dir
        self.auto_play = auto_play
        self.config_path = config_path

        self.categories = {}
        self.settings = load_config(self.config_path)
        self.sliders = {}

        self.is_playing = False
        self.current_song_name = ""
        self.current_category = ""
        self.poll_active = False
        self._log_counter = 0
        self._error_count = 0
        self._save_timer = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._hide_window)
        self._refresh_music()
        self.root.after(5000, self._start_background_tasks)

    def log(self, message: str, level: str = "info") -> None:
        def _do_log():
            if not getattr(self, "txt_log", None): return
            timestamp = time.strftime("%H:%M:%S")
            self._log_counter += 1
            tag = f"t{self._log_counter}"
            color = "#A78BFA"
            if level == "error": color = "#f87171"
            elif level == "success": color = "#4ADE80"
            self.txt_log.configure(state="normal")
            self.txt_log.insert(tk.END, f"[{timestamp}] {message}\n", tag)
            self.txt_log.tag_config(tag, foreground=color)
            self.txt_log.see(tk.END)
            self.txt_log.configure(state="disabled")
            print(f"[{timestamp}] {message}")
        self.root.after(0, _do_log)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG_COLOR)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=BG_COLOR)

        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        tk.Label(self.scroll_frame, text=":: Auto Media Player", font=("Helvetica", 16, "bold"), bg=BG_COLOR, fg=ACCENT).pack(pady=(10, 1))
        tk.Label(self.scroll_frame, text="Director de Orquesta para OBS Studio", font=("Helvetica", 9), bg=BG_COLOR, fg=TEXT_MUTED).pack(pady=(0, 8))

        now_frame = tk.Frame(self.scroll_frame, bg=PANEL_BG, highlightbackground=ACCENT_DIM, highlightthickness=1)
        now_frame.pack(fill="x", padx=12, pady=(4, 8))

        self.lbl_song = tk.Label(now_frame, text="Buscando musica...", font=("Helvetica", 13, "bold"), bg=PANEL_BG, fg=TEXT_MAIN, wraplength=420, justify="center")
        self.lbl_song.pack(padx=12, pady=(10, 2))

        self.lbl_folder = tk.Label(now_frame, text="Sincronizando...", font=("Helvetica", 9), bg=PANEL_BG, fg=ACCENT)
        self.lbl_folder.pack(padx=12, pady=(0, 3))

        self.lbl_time = tk.Label(now_frame, text="0:00 / 0:00", font=("Helvetica", 8), bg=PANEL_BG, fg=TEXT_MUTED)
        self.lbl_time.pack(pady=(0, 6))

        btn_frame = tk.Frame(self.scroll_frame, bg=BG_COLOR)
        btn_frame.pack(pady=6)

        self.btn_play = tk.Button(btn_frame, text="> Reproducir", font=("Helvetica", 10, "bold"), bg=ACCENT_DIM, fg="white", activebackground=ACCENT, activeforeground="white", relief="flat", padx=14, pady=4, command=self._on_play)
        self.btn_play.pack(side="left", padx=4)

        tk.Button(btn_frame, text=">> Siguiente", font=("Helvetica", 10), bg=PANEL_BG, fg=TEXT_MAIN, activebackground="#334155", activeforeground=TEXT_MAIN, relief="flat", padx=10, pady=4, command=self._on_next).pack(side="left", padx=4)
        tk.Button(btn_frame, text="<> Sync", font=("Helvetica", 10), bg=PANEL_BG, fg=TEXT_MAIN, activebackground="#334155", activeforeground=TEXT_MAIN, relief="flat", padx=10, pady=4, command=self._refresh_music).pack(side="left", padx=4)

        tk.Label(self.scroll_frame, text="Probabilidades por Categoria", font=("Helvetica", 12, "bold"), bg=BG_COLOR, fg=TEXT_MAIN).pack(pady=(12, 2), padx=12, anchor="w")
        self.sliders_frame = tk.Frame(self.scroll_frame, bg=BG_COLOR)
        self.sliders_frame.pack(fill="x", padx=12, pady=(6, 4))

        tk.Label(self.scroll_frame, text="> Registro de Archivos (Debug)", font=("Helvetica", 10, "bold"), bg=BG_COLOR, fg=TEXT_MUTED).pack(pady=(14, 2), padx=12, anchor="w")
        log_container = tk.Frame(self.scroll_frame, bg="#000000")
        log_container.pack(fill="x", padx=12, pady=(0, 14))

        self.txt_log = scrolledtext.ScrolledText(log_container, height=7, bg="#000000", fg=TEXT_MAIN, font=("Courier", 8), state="disabled", borderwidth=0, highlightthickness=1, highlightbackground="#334155")
        self.txt_log.pack(fill="x")

        self.lbl_status = tk.Label(self.root, text="", font=("Helvetica", 8), bg=BG_COLOR, fg=GREEN)
        self.lbl_status.pack(side="bottom", pady=3)

    def run(self) -> None:
        threading.Thread(target=self._setup_tray, daemon=True).start()
        self.root.mainloop()

    def _setup_tray(self) -> None:
        image = self._create_tray_image()
        menu = pystray.Menu(
            item("Mostrar Panel", self._show_window, default=True),
            item("Siguiente Cancion", lambda: self._on_next()),
            item("Salir", self._quit_app),
        )
        self.tray_icon = pystray.Icon("auto_media_radio", image, "Auto Media Radio", menu)
        self.tray_icon.run()

    def _create_tray_image(self) -> Image.Image:
        width, height = 64, 64
        image = Image.new("RGB", (width, height), BG_COLOR)
        dc = ImageDraw.Draw(image)
        dc.ellipse((10, 10, 54, 54), fill=ACCENT_DIM)
        dc.rectangle((35, 20, 40, 45), fill="white")
        dc.ellipse((25, 40, 40, 50), fill="white")
        return image

    def _hide_window(self) -> None:
        self.root.withdraw()
        self.log("Aplicacion minimizada a la bandeja del sistema.")

    def _show_window(self) -> None:
        def _restore():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        self.root.after(0, _restore)

    def _quit_app(self) -> None:
        try:
            if getattr(self, "tray_icon", None):
                self.tray_icon.stop()
        except Exception: pass
        self.root.after(0, self.root.destroy)

    def _build_sliders(self) -> None:
        for widget in self.sliders_frame.winfo_children():
            widget.destroy()
        self.sliders.clear()

        for cat_name in sorted(self.categories.keys()):
            songs = self.categories[cat_name]
            if not songs: continue
            default_val = self.settings.get(cat_name, 100)
            group = tk.Frame(self.sliders_frame, bg=PANEL_BG, highlightbackground="#334155", highlightthickness=1)
            group.pack(fill="x", pady=3)
            header = tk.Frame(group, bg=PANEL_BG)
            header.pack(fill="x", padx=10, pady=(6, 2))
            tk.Label(header, text=cat_name, font=("Helvetica", 10, "bold"), bg=PANEL_BG, fg=TEXT_MAIN, anchor="w").pack(side="left")
            badge = tk.Label(header, text=f"{default_val}%", font=("Helvetica", 9, "bold"), bg=ACCENT_DIM, fg="white", padx=6, pady=1)
            badge.pack(side="right")
            tk.Label(group, text=f"{len(songs)} pistas en total", font=("Helvetica", 8), bg=PANEL_BG, fg=TEXT_MUTED, anchor="w").pack(padx=10, anchor="w")
            var = tk.IntVar(value=default_val)
            slider = tk.Scale(group, from_=0, to=100, orient="horizontal", variable=var, bg=PANEL_BG, fg=TEXT_MAIN, troughcolor="#334155", activebackground=ACCENT, highlightthickness=0, sliderrelief="flat", length=280, showvalue=False, command=lambda val, c=cat_name, b=badge, v=var: self._on_slider_change(c, v, b))
            slider.pack(fill="x", padx=10, pady=(2, 3))
            self.sliders[cat_name] = var

    def _on_slider_change(self, cat_name: str, var: tk.IntVar, badge_label: tk.Label) -> None:
        val = var.get()
        badge_label.config(text=f"{val}%")
        self.settings[cat_name] = val
        if self._save_timer:
            self.root.after_cancel(self._save_timer)
        self._save_timer = self.root.after(500, self._save_settings)

    def _save_settings(self) -> None:
        self._save_timer = None
        save_config(self.config_path, self.settings)
        self._show_status("OK - Guardado")

    def _show_status(self, text: str) -> None:
        self.lbl_status.config(text=text)
        self.root.after(2000, lambda: self.lbl_status.config(text=""))

    def _on_play(self) -> None:
        if not self.categories: return
        if self.is_playing:
            self.obs.pause_media()
            self.root.after(0, lambda: self.btn_play.config(text="> Reproducir"))
            self.is_playing = False
            self.log("Reproduccion pausada.")
        else:
            if self.current_song_name and self.obs.resume_media():
                self.is_playing = True
                self.root.after(0, lambda: self.btn_play.config(text="|| Pausar"))
                self.poll_active = True
                self.root.after(1000, self._poll_media_state)
                self.log("Reproduccion reanudada.")
            else:
                self.root.after(0, self._play_next)

    def _on_next(self) -> None:
        if self.categories:
            self.root.after(0, self._play_next)

    def _play_next(self) -> None:
        selected_cat = get_weighted_category(self.categories, self.settings)
        if not selected_cat:
            self.lbl_song.config(text="Todas las listas estan al 0%")
            return

        songs = self.categories[selected_cat]
        chosen = random.choice(songs)
        filename = os.path.splitext(os.path.basename(chosen))[0]

        self.current_song_name = filename
        self.current_category = selected_cat
        self.lbl_song.config(text=filename)
        self.lbl_folder.config(text=f"[{selected_cat}]")
        self.lbl_time.config(text="0:00 / 0:00")
        self.log(f"> Reproduciendo: {filename} [{selected_cat}]")

        # Actualizar Widget Text
        if self.widget:
            subdirectory = os.path.basename(os.path.dirname(chosen))
            self.widget.update_song_info(subdirectory, filename)

        success = self.obs.play_file(chosen)
        if success:
            self.is_playing = True
            self.btn_play.config(text="|| Pausar")
            self.poll_active = True
            self.root.after(1000, self._poll_media_state)
        else:
            self.lbl_song.config(text="Error de conexion. Reconectando...")
            self.log("[!] Fallo al reproducir. Iniciando auto-reconexión...", "error")
            self.obs.connected = False
            self.is_playing = False
            self.poll_active = False
            self.btn_play.config(text="> Reproducir")
            self.root.after(3000, self._start_background_tasks)

    def _refresh_music(self) -> None:
        self.categories = scan_music(self.music_dir)
        total = sum(len(v) for v in self.categories.values())
        self._build_sliders()
        self.log(f"[OK] Total: {total} canciones", "success")
        self.lbl_folder.config(text=f"{total} canciones integradas")
        self._show_status("OK - Sync completa")

    def _poll_media_state(self) -> None:
        if not self.is_playing:
            self.poll_active = False
            return
        try:
            state, cursor, duration = self.obs.get_media_status()
            if duration > 0:
                self.lbl_time.config(text=f"{self._fmt(cursor)} / {self._fmt(duration)}")
            
            self._error_count = 0
            if state == "OBS_MEDIA_STATE_ENDED":
                self.log(f"Cancion terminada: {self.current_song_name}")
                self.poll_active = False
                self._play_next()
                return
        except Exception as e:
            self._error_count += 1
            if self._error_count >= 10:
                self.log("[!] Conexion perdida. Reconectando...", "error")
                self.obs.connected = False
                self.is_playing = False
                self.poll_active = False
                self._error_count = 0
                self.root.after(0, lambda: self.btn_play.config(text="> Reproducir"))
                self.root.after(3000, self._start_background_tasks)
                return
        self.root.after(1000, self._poll_media_state)

    @staticmethod
    def _fmt(ms: int) -> str:
        total_secs = max(0, ms) // 1000
        mins = total_secs // 60
        secs = total_secs % 60
        return f"{mins}:{secs:02d}"

    def _start_background_tasks(self) -> None:
        def worker():
            from obs_controller import _read_obs_password
            self.log("Buscando conexion con OBS WebSocket...")
            while True:
                obs_password = _read_obs_password()
                try:
                    if self.obs.connect(password=obs_password):
                        self.log("[OK] Conectado a OBS WebSocket!", "success")
                        self.root.after(0, lambda: self.lbl_song.config(text="Listo para reproducir"))
                        if self.auto_play and self.categories:
                            self.root.after(1000, self._play_next)
                        break
                    else:
                        self.root.after(0, lambda: self.lbl_song.config(text="... Buscando OBS"))
                except Exception as e:
                    self.log(f"Error de conexion: {e}", "error")
                time.sleep(5)
        threading.Thread(target=worker, daemon=True).start()
