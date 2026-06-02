#!/usr/bin/env python3
import os
import sys
import random

# Importar lógica compartida
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.music_scanner import scan_music
from shared.config_handler import load_config, get_weighted_category

MUSIC_DIR = os.environ.get("MUSIC_DIR", "/headless/Music")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared", "data", "radio_config.json")
NOW_PLAYING_FILE = "/tmp/now_playing.txt"

def main():
    # 1. Escanear música y cargar configuración
    categories = scan_music(MUSIC_DIR)
    if not categories:
        # Si no hay música, salir (Liquidsoap maneja el silencio o fallback)
        sys.exit(1)

    settings = load_config(CONFIG_PATH)

    # 2. Elegir categoría aleatoria basada en porcentajes
    selected_cat = get_weighted_category(categories, settings)
    if not selected_cat:
        # Fallback: Elegir categoría aleatoria si todas están a 0
        selected_cat = random.choice(list(categories.keys()))
    
    # 3. Elegir canción
    songs = categories[selected_cat]
    chosen_file = random.choice(songs)
    
    # 4. Actualizar texto para FFmpeg (formato "Carpeta\nTrack: Cancion")
    filename = os.path.splitext(os.path.basename(chosen_file))[0]
    subdirectory = os.path.basename(os.path.dirname(chosen_file))
    text_content = f"{subdirectory}\nTrack: {filename}"
    
    # Escribir a now_playing.txt para que FFmpeg lo lea con reload=1
    os.makedirs(os.path.dirname(NOW_PLAYING_FILE), exist_ok=True)
    with open(NOW_PLAYING_FILE, "w", encoding="utf-8") as f:
        f.write(text_content)
        
    # 5. Imprimir ruta absoluta de la canción a stdout para que Liquidsoap la capture
    print(chosen_file)

if __name__ == "__main__":
    main()
