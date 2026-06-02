import os
import subprocess
import tempfile
import shutil
import json

# Ruta relativa al directorio de música
MUSIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'media', 'musica'))

def is_already_optimized(filepath):
    """Comprueba si el MP3 ya está en 128kbps CBR y sin portada."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            filepath
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            return False
        
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        
        # Comprobar si tiene portada (stream de video)
        has_cover = any(s.get("codec_type") == "video" for s in streams)
        if has_cover:
            return False
        
        # Comprobar bitrate del audio
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if not audio_streams:
            return False
        
        bit_rate = audio_streams[0].get("bit_rate")
        if bit_rate and abs(int(bit_rate) - 128000) < 5000:
            return True
        
        return False
    except Exception:
        return False

def optimize_mp3s():
    print(f"Iniciando optimizacion en: {MUSIC_DIR}")
    if not os.path.exists(MUSIC_DIR):
        print("Directorio no encontrado.")
        return

    count = 0
    skipped = 0
    for root, dirs, files in os.walk(MUSIC_DIR):
        for file in files:
            if file.lower().endswith('.mp3'):
                filepath = os.path.join(root, file)
                
                if is_already_optimized(filepath):
                    print(f"  [SKIP] Ya optimizado: {file}")
                    skipped += 1
                    continue
                
                print(f"Optimizando: {file}")
                
                fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                os.close(fd)
                
                # Comando FFmpeg para CBR 128k, 44100Hz, Estéreo
                # -map 0:a y -vn : Extrae el audio y elimina forzosamente la portada (video stream)
                # Al no usar -map_metadata -1, se preservan los tags de texto (Título, Artista, Álbum)
                cmd = [
                    "ffmpeg", "-y", "-i", filepath,
                    "-map", "0:a",
                    "-vn",
                    "-codec:a", "libmp3lame",
                    "-b:a", "128k",
                    "-ar", "44100",
                    "-ac", "2",
                    temp_path
                ]
                
                try:
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if result.returncode == 0:
                        shutil.move(temp_path, filepath)
                        print(f"  [OK] Sobrescrito a 128kbps CBR")
                        count += 1
                    else:
                        print(f"  [ERROR] Fallo al procesar")
                        os.remove(temp_path)
                except Exception as e:
                    print(f"  [ERROR] Excepcion: {e}")
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                        
    print(f"\nOptimizacion completada. {count} procesados, {skipped} ya estaban optimizados.")

if __name__ == "__main__":
    optimize_mp3s()

