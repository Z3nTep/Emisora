#!/usr/bin/env python3
"""
Auto Media Player — Director de Orquesta para OBS Studio
Controlador nativo ultra-ligero que gestiona la reproducción musical
automática dentro de OBS mediante WebSocket.
"""

import os

from obs_controller import OBSController
from ui_controller import PlayerUI
from obs_widget import WidgetUpdater

# --- Configuración --------------------------------------------------------
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/headless/Music")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared", "data", "radio_config.json")
OBS_HOST = "127.0.0.1"
OBS_PORT = 4455
OBS_SOURCE_NAME = os.environ.get("OBS_SOURCE_NAME", "Media")
AUTO_PLAY = os.environ.get("AUTO_PLAY_RADIO", "false").lower() == "true"

# Widget OBS Variables
TEXT_SOURCE_NAME = "Texto Cancion" # Nombre de la fuente de Texto Libre 2

def main():
    print("[*] Iniciando componentes modulares de Auto Media Player (OBS Mode)...")

    # 1. Instanciar controlador de OBS (Core)
    obs_controller = OBSController(
        host=OBS_HOST,
        port=OBS_PORT,
        source_name=OBS_SOURCE_NAME
    )

    # 2. Instanciar controlador del Widget
    widget_updater = WidgetUpdater(
        obs_controller=obs_controller,
        text_source_name=TEXT_SOURCE_NAME
    )

    # 3. Lanzar interfaz gráfica
    app_ui = PlayerUI(
        obs_controller=obs_controller,
        widget_updater=widget_updater,
        music_dir=MUSIC_DIR,
        auto_play=AUTO_PLAY,
        config_path=CONFIG_PATH
    )

    app_ui.run()

if __name__ == "__main__":
    main()
