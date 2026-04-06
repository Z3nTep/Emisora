#!/usr/bin/env python3
"""
Auto Media Player — Director de Orquesta para OBS Studio
Controlador nativo ultra-ligero que gestiona la reproducción musical
automática dentro de OBS mediante WebSocket. Sin navegadores, sin Node.js.
"""

import json
import os
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

try:
    import obsws_python as obs
except ImportError:
    obs = None


# --- Configuración --------------------------------------------------------
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/headless/Music")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "radio_config.json")
OBS_HOST = "127.0.0.1"
OBS_PORT = 4455
OBS_SOURCE_NAME = os.environ.get("OBS_SOURCE_NAME", "Media")
AUTO_PLAY = os.environ.get("AUTO_PLAY_RADIO", "false").lower() == "true"
OBS_GLOBAL_INI = os.path.expanduser("~/.config/obs-studio/global.ini")
# Ruta para versiones modernas de OBS (32+)
OBS_WEBSOCKET_JSON = os.path.expanduser("~/.config/obs-studio/plugin_config/obs-websocket/config.json")

VALID_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".wma", ".webm", ".weba"}

# --- Colores (Estilo oscuro premium) --------------------------------------
BG_COLOR = "#0f172a"
PANEL_BG = "#1e293b"
TEXT_MAIN = "#f8fafc"
TEXT_MUTED = "#94a3b8"
ACCENT = "#c084fc"
ACCENT_DIM = "#7c3aed"
GREEN = "#4ade80"


# ===========================================================================
#  Capa de Datos: Escaneo de música y persistencia de configuración
# ===========================================================================

def scan_music(music_dir: str) -> dict:
    """Escanea recursivamente el directorio de música y agrupa por carpeta raíz."""
    categories: dict[str, list[str]] = {}
    music_path = Path(music_dir)
    if not music_path.exists():
        return categories

    for f in music_path.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in VALID_EXTENSIONS:
            continue
        relative = f.relative_to(music_path)
        parts = relative.parts
        category = parts[0] if len(parts) > 1 else "Raiz (Musica suelta)"
        if category not in categories:
            categories[category] = []
        categories[category].append(str(f))

    return categories


def load_config() -> dict:
    """Carga la configuración de porcentajes desde disco."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(settings: dict) -> None:
    """Guarda la configuración de porcentajes en disco."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2, ensure_ascii=False)


# ===========================================================================
#  Capa de Control: Comunicación con OBS vía WebSocket
# ===========================================================================

class OBSController:
    """Gestiona la conexión y los comandos hacia OBS Studio."""

    def __init__(self) -> None:
        self.client = None
        self.connected = False
        self._password: str = ""

    def connect(self, retries: int = 30, delay: int = 3, password: str = "") -> bool:
        """Intenta conectar a OBS WebSocket con reintentos."""
        if obs is None:
            print("[OBS] Libreria obsws-python no disponible.")
            return False
        self._password = password

        for attempt in range(1, retries + 1):
            try:
                self.client = obs.ReqClient(
                    host=OBS_HOST,
                    port=OBS_PORT,
                    password=self._password,
                    timeout=5,
                )
                self.connected = True
                print(f"[OBS] Conectado al WebSocket (intento {attempt})")
                return True
            except Exception as e:
                print(f"[OBS] Intento {attempt}/{retries} fallido: {e}")
                time.sleep(delay)

        print("[OBS] No se pudo conectar a OBS.")
        return False

    def play_file(self, filepath: str) -> bool:
        """Carga y reproduce un archivo en la fuente multimedia de OBS."""
        if not self.connected:
            return False
        try:
            self.client.set_input_settings(
                name=OBS_SOURCE_NAME,
                settings={"local_file": filepath, "is_local_file": True},
                overlay=True,
            )
            self.client.trigger_media_input_action(
                name=OBS_SOURCE_NAME,
                action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
            )
            return True
        except Exception as e:
            print(f"[OBS] Error reproduciendo: {e}")
            return False

    def pause_media(self) -> bool:
        """Pausa la reproduccion multimedia en OBS."""
        if not self.connected:
            return False
        try:
            self.client.trigger_media_input_action(
                name=OBS_SOURCE_NAME,
                action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE",
            )
            return True
        except Exception:
            return False

    def resume_media(self) -> bool:
        """Reanuda la reproduccion multimedia en OBS."""
        if not self.connected:
            return False
        try:
            self.client.trigger_media_input_action(
                name=OBS_SOURCE_NAME,
                action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY",
            )
            return True
        except Exception:
            return False

    def get_media_status(self) -> tuple[str, int, int]:
        """Devuelve (estado, cursor_ms, duracion_ms) en una sola llamada."""
        if not self.connected:
            return ("unknown", 0, 0)
        try:
            resp = self.client.get_media_input_status(name=OBS_SOURCE_NAME)
            return (
                resp.media_state or "unknown",
                resp.media_cursor or 0,
                resp.media_duration or 0,
            )
        except Exception:
            return ("unknown", 0, 0)


# ===========================================================================
#  Capa de Lógica: Algoritmo de selección ponderada
# ===========================================================================

def get_weighted_category(categories: dict, settings: dict) -> str | None:
    """Selección aleatoria de carpeta ponderada por los deslizadores."""
    weights: list[int] = []
    cat_names: list[str] = []
    total_weight = 0

    for cat in categories:
        val = settings.get(cat, 100)
        if val > 0:
            weights.append(val)
            cat_names.append(cat)
            total_weight += val

    if total_weight == 0:
        return None

    rand = random.random() * total_weight
    for i, w in enumerate(weights):
        rand -= w
        if rand <= 0:
            return cat_names[i]
    return cat_names[-1]


# ===========================================================================
#  Capa de Presentación: Interfaz Gráfica Nativa (Tkinter)
# ===========================================================================

class AutoMediaPlayerApp:
    """Aplicación de escritorio que funciona como panel de control."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Auto Media Player")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("480x650")
        self.root.minsize(400, 500)

        self.categories: dict[str, list[str]] = {}
        self.settings = load_config()
        self.sliders: dict[str, tk.IntVar] = {}
        self.obs = OBSController()
        self.is_playing = False
        self.current_song_name = ""
        self.current_category = ""
        self.poll_active = False
        self._log_counter = 0
        self._error_count = 0
        self._save_timer: str | None = None

        # Atributos de UI (inicializados en _build_ui)
        self.txt_log: scrolledtext.ScrolledText | None = None
        self.lbl_song: tk.Label | None = None
        self.lbl_folder: tk.Label | None = None
        self.lbl_time: tk.Label | None = None
        self.btn_play: tk.Button | None = None
        self.progress_var = tk.DoubleVar(value=0)
        self.tray_icon: pystray.Icon | None = None

        self._build_ui()

        # Interceptar el botón de cerrar [X]
        self.root.protocol("WM_DELETE_WINDOW", self._hide_window)

        # Escaneo inmediato de carpetas
        self._refresh_music()

        # Conectar a OBS cuando el mainloop esté listo
        self.root.after(5000, self._start_background_tasks)

    # -- Log (hilo-seguro) -------------------------------------------------

    def log(self, message: str, level: str = "info") -> None:
        """Añade un mensaje al log de la interfaz (hilo-seguro)."""
        def _do_log() -> None:
            if not self.txt_log:
                return
            timestamp = time.strftime("%H:%M:%S")
            self._log_counter += 1
            tag = f"t{self._log_counter}"

            color = "#A78BFA"
            if level == "error":
                color = "#f87171"
            elif level == "success":
                color = "#4ADE80"

            self.txt_log.configure(state="normal")
            self.txt_log.insert(tk.END, f"[{timestamp}] {message}\n", tag)
            self.txt_log.tag_config(tag, foreground=color)
            self.txt_log.see(tk.END)
            self.txt_log.configure(state="disabled")
            print(f"[{timestamp}] {message}")

        self.root.after(0, _do_log)

    # -- Construcción de la interfaz ---------------------------------------

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

        # Scroll con rueda del ratón
        def _on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # -- Título --
        tk.Label(
            self.scroll_frame, text=":: Auto Media Player", font=("Helvetica", 16, "bold"),
            bg=BG_COLOR, fg=ACCENT,
        ).pack(pady=(10, 1))

        tk.Label(
            self.scroll_frame, text="Director de Orquesta para OBS Studio",
            font=("Helvetica", 9), bg=BG_COLOR, fg=TEXT_MUTED,
        ).pack(pady=(0, 8))

        # -- Panel "Reproduciendo Ahora" --
        now_frame = tk.Frame(self.scroll_frame, bg=PANEL_BG, highlightbackground=ACCENT_DIM, highlightthickness=1)
        now_frame.pack(fill="x", padx=12, pady=(4, 8))

        self.lbl_song = tk.Label(
            now_frame, text="Buscando musica...", font=("Helvetica", 13, "bold"),
            bg=PANEL_BG, fg=TEXT_MAIN, wraplength=420, justify="center",
        )
        self.lbl_song.pack(padx=12, pady=(10, 2))

        self.lbl_folder = tk.Label(
            now_frame, text="Sincronizando...", font=("Helvetica", 9), bg=PANEL_BG, fg=ACCENT,
        )
        self.lbl_folder.pack(padx=12, pady=(0, 3))

        # Barra de progreso
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Custom.Horizontal.TProgressbar", troughcolor=PANEL_BG, background=ACCENT, thickness=5)
        self.progress_bar = ttk.Progressbar(
            now_frame, variable=self.progress_var, maximum=100, style="Custom.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill="x", padx=12, pady=(2, 3))

        self.lbl_time = tk.Label(
            now_frame, text="0:00 / 0:00", font=("Helvetica", 8), bg=PANEL_BG, fg=TEXT_MUTED,
        )
        self.lbl_time.pack(pady=(0, 6))

        # -- Botones de control --
        btn_frame = tk.Frame(self.scroll_frame, bg=BG_COLOR)
        btn_frame.pack(pady=6)

        self.btn_play = tk.Button(
            btn_frame, text="> Reproducir", font=("Helvetica", 10, "bold"), bg=ACCENT_DIM, fg="white",
            activebackground=ACCENT, activeforeground="white", relief="flat", padx=14, pady=4,
            command=self._on_play,
        )
        self.btn_play.pack(side="left", padx=4)

        tk.Button(
            btn_frame, text=">> Siguiente", font=("Helvetica", 10), bg=PANEL_BG, fg=TEXT_MAIN,
            activebackground="#334155", activeforeground=TEXT_MAIN, relief="flat", padx=10, pady=4,
            command=self._on_next,
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="<> Sync", font=("Helvetica", 10), bg=PANEL_BG, fg=TEXT_MAIN,
            activebackground="#334155", activeforeground=TEXT_MAIN, relief="flat", padx=10, pady=4,
            command=self._refresh_music,
        ).pack(side="left", padx=4)


        # -- Sección de deslizadores --
        tk.Label(
            self.scroll_frame, text="Probabilidades por Categoria",
            font=("Helvetica", 12, "bold"), bg=BG_COLOR, fg=TEXT_MAIN,
        ).pack(pady=(12, 2), padx=12, anchor="w")

        self.sliders_frame = tk.Frame(self.scroll_frame, bg=BG_COLOR)
        self.sliders_frame.pack(fill="x", padx=12, pady=(6, 4))

        # -- Sección de Logs (Debug) --
        tk.Label(
            self.scroll_frame, text="> Registro de Archivos (Debug)",
            font=("Helvetica", 10, "bold"), bg=BG_COLOR, fg=TEXT_MUTED,
        ).pack(pady=(14, 2), padx=12, anchor="w")

        log_container = tk.Frame(self.scroll_frame, bg="#000000")
        log_container.pack(fill="x", padx=12, pady=(0, 14))

        self.txt_log = scrolledtext.ScrolledText(
            log_container, height=7, bg="#000000", fg=TEXT_MAIN,
            font=("Courier", 8), state="disabled", borderwidth=0, highlightthickness=1,
            highlightbackground="#334155"
        )
        self.txt_log.pack(fill="x")

        # -- Estado de guardado --
        self.lbl_status = tk.Label(
            self.root, text="", font=("Helvetica", 8), bg=BG_COLOR, fg=GREEN,
        )
        self.lbl_status.pack(side="bottom", pady=3)

    # -- Gestión de Ventana y Tray -----------------------------------------

    def run(self) -> None:
        """Punto de entrada principal."""
        threading.Thread(target=self._setup_tray, daemon=True).start()
        self.root.mainloop()

    def _setup_tray(self) -> None:
        """Configura el icono en la bandeja del sistema."""
        image = self._create_tray_image()
        menu = pystray.Menu(
            item("Mostrar Panel", self._show_window, default=True),
            item("Siguiente Cancion", lambda: self._on_next()),
            item("Salir", self._quit_app),
        )
        self.tray_icon = pystray.Icon("auto_media_radio", image, "Auto Media Radio", menu)
        self.tray_icon.run()

    def _create_tray_image(self) -> Image.Image:
        """Genera un icono simple (un círculo púrpura con una nota musical)."""
        width, height = 64, 64
        image = Image.new("RGB", (width, height), BG_COLOR)
        dc = ImageDraw.Draw(image)
        dc.ellipse((10, 10, 54, 54), fill=ACCENT_DIM)
        dc.rectangle((35, 20, 40, 45), fill="white")
        dc.ellipse((25, 40, 40, 50), fill="white")
        return image

    def _hide_window(self) -> None:
        """Oculta la ventana en lugar de cerrarla."""
        self.root.withdraw()
        self.log("Aplicacion minimizada a la bandeja del sistema.")

    def _show_window(self) -> None:
        """Muestra la ventana de nuevo (hilo-seguro)."""
        def _restore() -> None:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        self.root.after(0, _restore)

    def _quit_app(self) -> None:
        """Cierra la aplicación completamente."""
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        self.root.after(0, self.root.destroy)

    # -- Construcción dinámica de sliders ----------------------------------

    def _build_sliders(self) -> None:
        for widget in self.sliders_frame.winfo_children():
            widget.destroy()
        self.sliders.clear()

        for cat_name in sorted(self.categories.keys()):
            songs = self.categories[cat_name]
            if not songs:
                continue

            default_val = self.settings.get(cat_name, 100)

            group = tk.Frame(self.sliders_frame, bg=PANEL_BG, highlightbackground="#334155", highlightthickness=1)
            group.pack(fill="x", pady=3)

            header = tk.Frame(group, bg=PANEL_BG)
            header.pack(fill="x", padx=10, pady=(6, 2))

            tk.Label(
                header, text=cat_name, font=("Helvetica", 10, "bold"), bg=PANEL_BG, fg=TEXT_MAIN, anchor="w",
            ).pack(side="left")

            badge = tk.Label(
                header, text=f"{default_val}%", font=("Helvetica", 9, "bold"),
                bg=ACCENT_DIM, fg="white", padx=6, pady=1,
            )
            badge.pack(side="right")

            tk.Label(
                group, text=f"{len(songs)} pistas en todas sus subcarpetas",
                font=("Helvetica", 8), bg=PANEL_BG, fg=TEXT_MUTED, anchor="w",
            ).pack(padx=10, anchor="w")

            var = tk.IntVar(value=default_val)
            slider = tk.Scale(
                group, from_=0, to=100, orient="horizontal", variable=var,
                bg=PANEL_BG, fg=TEXT_MAIN, troughcolor="#334155", activebackground=ACCENT,
                highlightthickness=0, sliderrelief="flat", length=280, showvalue=False,
                command=lambda val, c=cat_name, b=badge, v=var: self._on_slider_change(c, v, b),
            )
            slider.pack(fill="x", padx=10, pady=(2, 3))

            labels_frame = tk.Frame(group, bg=PANEL_BG)
            labels_frame.pack(fill="x", padx=10, pady=(0, 6))
            tk.Label(labels_frame, text="Ignorar (0%)", font=("Helvetica", 7), bg=PANEL_BG, fg=TEXT_MUTED).pack(side="left")
            tk.Label(labels_frame, text="Frecuente (100%)", font=("Helvetica", 7), bg=PANEL_BG, fg=TEXT_MUTED).pack(side="right")

            self.sliders[cat_name] = var

    def _on_slider_change(self, cat_name: str, var: tk.IntVar, badge_label: tk.Label) -> None:
        val = var.get()
        badge_label.config(text=f"{val}%")
        self.settings[cat_name] = val
        # Debounce: cancelar guardado previo pendiente y programar uno nuevo
        if self._save_timer:
            self.root.after_cancel(self._save_timer)
        self._save_timer = self.root.after(500, self._save_settings)

    def _save_settings(self) -> None:
        """Guarda la configuracion tras el debounce del slider."""
        self._save_timer = None
        save_config(self.settings)
        self._show_status("OK - Guardado")

    def _show_status(self, text: str) -> None:
        self.lbl_status.config(text=text)
        self.root.after(2000, lambda: self.lbl_status.config(text=""))

    # -- Acciones del usuario ----------------------------------------------

    def _on_play(self) -> None:
        if not self.categories:
            return
        if self.is_playing:
            self.obs.pause_media()
            self.root.after(0, lambda: self.btn_play.config(text="> Reproducir"))
            self.is_playing = False
            self.log("Reproduccion pausada.")
        else:
            # Si hay cancion en pausa, reanudar; si no, reproducir nueva
            if self.current_song_name and self.obs.resume_media():
                self.is_playing = True
                self.root.after(0, lambda: self.btn_play.config(text="|| Pausar"))
                self.poll_active = True
                self.root.after(500, self._poll_media_state)
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
            self.lbl_folder.config(text="Sube los porcentajes en los controles")
            return

        songs = self.categories[selected_cat]
        chosen = random.choice(songs)
        filename = os.path.splitext(os.path.basename(chosen))[0]

        self.current_song_name = filename
        self.current_category = selected_cat
        self.lbl_song.config(text=filename)
        self.lbl_folder.config(text=f"[{selected_cat}]")

        # Resetear progreso visual
        self.progress_var.set(0)
        self.lbl_time.config(text="0:00 / 0:00")

        self.log(f"> Reproduciendo: {filename} [{selected_cat}]")

        success = self.obs.play_file(chosen)
        if success:
            self.is_playing = True
            self.btn_play.config(text="|| Pausar")
            # Siempre reiniciar el polling
            self.poll_active = True
            self.root.after(1000, self._poll_media_state)
        else:
            self.lbl_song.config(text="Error conectando con OBS")

    def _refresh_music(self) -> None:
        self.log("Sincronizando con el servidor de musica...")
        self.categories = scan_music(MUSIC_DIR)

        total = sum(len(v) for v in self.categories.values())
        self.log(f"Encontrados {total} archivos totales.")

        for cat, tracks in self.categories.items():
            self.log(f'  Carpeta "{cat}": {len(tracks)} archivos encontrados.')

        self._build_sliders()

        self.log(f"[OK] Total: {total} canciones en {len(self.categories)} categorias.", "success")

        if total == 0:
            self.log("[!] No se encontraron canciones.", "error")

        self.lbl_folder.config(text=f"{total} canciones integradas")
        self._show_status("OK - Sync completa")

    # -- Polling de estado de OBS ------------------------------------------

    def _poll_media_state(self) -> None:
        """Comprueba periódicamente si la canción ha terminado."""
        if not self.is_playing:
            self.poll_active = False
            return

        try:
            state, cursor, duration = self.obs.get_media_status()

            # Actualizar barra de progreso
            if duration > 0:
                pct = (cursor / duration) * 100
                self.progress_var.set(pct)
                self.lbl_time.config(text=f"{self._fmt(cursor)} / {self._fmt(duration)}")

            # Conexion OK, resetear contador de errores
            self._error_count = 0

            # Si la canción ha terminado, reproducir la siguiente
            if state == "OBS_MEDIA_STATE_ENDED":
                self.log(f"Cancion terminada: {self.current_song_name}")
                self.poll_active = False
                self._play_next()
                return
            elif state == "OBS_MEDIA_STATE_NONE" and duration == 0 and cursor == 0 and self.is_playing:
                # La fuente puede reportar NONE brevemente al cambiar de canción
                pass
        except Exception as e:
            self._error_count += 1
            if self._error_count >= 5:
                self.log("[!] Conexion con OBS perdida. Reconectando...", "error")
                self.obs.connected = False
                self.is_playing = False
                self.poll_active = False
                self._error_count = 0
                self.root.after(0, lambda: self.btn_play.config(text="> Reproducir"))
                self.root.after(3000, self._start_background_tasks)
                return
            self.log(f"Error polling OBS: {e}", "error")

        self.root.after(500, self._poll_media_state)

    @staticmethod
    def _fmt(ms: int) -> str:
        """Formatea milisegundos a M:SS."""
        total_secs = max(0, ms) // 1000
        mins = total_secs // 60
        secs = total_secs % 60
        return f"{mins}:{secs:02d}"

    @staticmethod
    def _read_obs_password() -> str:
        """Lee la contraseña del WebSocket desde config.json o global.ini."""
        import re, json
        
        # 1. Intentar con el nuevo formato JSON (OBS 32+)
        if os.path.exists(OBS_WEBSOCKET_JSON):
            try:
                with open(OBS_WEBSOCKET_JSON, "r") as f:
                    data = json.load(f)
                    return data.get("server_password", "")
            except:
                pass

        # 2. Intentar con el formato INI tradicional
        if os.path.exists(OBS_GLOBAL_INI):
            try:
                with open(OBS_GLOBAL_INI, "r") as f:
                    content = f.read()
                # Buscar ServerPassword o server_password
                match = re.search(r"(?:ServerPassword|server_password)\s*=\s*(.+)", content, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
            except:
                pass
                
        return ""

    def _start_background_tasks(self) -> None:
        """Inicia la conexión a OBS en un hilo separado con reintentos."""
        def worker() -> None:
            self.log("Buscando conexion con OBS WebSocket...")

            while True:
                # Leer la contraseña en cada intento hasta conectar (por si OBS está arrancando)
                obs_password = self._read_obs_password()
                
                try:
                    connected = self.obs.connect(retries=1, delay=0, password=obs_password)
                    if connected:
                        self.log("[OK] Conectado a OBS WebSocket!", "success")
                        if obs_password:
                            self.log("Autenticación completada con éxito.")
                        
                        self.root.after(0, lambda: self.lbl_song.config(text="Listo para reproducir"))

                        if AUTO_PLAY and self.categories:
                            self.root.after(1000, self._play_next)
                        break
                    else:
                        self.root.after(0, lambda: self.lbl_song.config(text="... Buscando OBS"))
                        self.log("Buscando OBS WebSocket en 127.0.0.1:4455...")
                except Exception as e:
                    self.root.after(0, lambda ex=e: self.lbl_song.config(text=f"[!] Error: {str(ex)[:30]}"))
                    self.log(f"Error de conexion: {e}", "error")

                time.sleep(5)

        threading.Thread(target=worker, daemon=True).start()


# ===========================================================================
#  Punto de entrada
# ===========================================================================

if __name__ == "__main__":
    print("[*] Auto Media Player iniciado")
    app = AutoMediaPlayerApp()
    app.run()
