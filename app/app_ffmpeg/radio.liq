# radio.liq
# Script principal de Liquidsoap para la Emisora

# Permitir ejecución como root (útil para contenedores Docker)
settings.init.allow_root := true

# Configuración de logs
settings.log.level := 3
settings.log.stdout := true

# Crear archivo de texto en RAM para evitar que FFmpeg falle si aún no hay canción
ignore(process.read("touch /tmp/now_playing.txt"))

# Generador dinámico: llama a Python cada vez que necesita una canción
def get_next_song() =
  # process.read.lines ejecuta el comando y devuelve sus líneas stdout
  result = process.read.lines("python3 /app/app_ffmpeg/next_song.py")
  
  if list.length(result) > 0 then
    song_path = list.hd(result)
    print("Siguiente canción: #{song_path}")
    request.create(song_path)
  else
    print("Error: El script Python no devolvió ninguna ruta. Esperando 5s...")
    # Crear un request vacío o de error (se saltará y volverá a intentar)
    request.create("")
  end
end

# Fuente de audio: cola infinita usando el generador dinámico
radio = request.dynamic(get_next_song)

# Hacer la fuente infallible con fallback a silencio
radio = fallback(track_sensitive=false, [radio, blank()])

# Aplicar crossfade suave entre canciones (duración de 3 segundos)
radio = crossfade(duration=3., fade_in=3., fade_out=3., radio)
radio = fallback(track_sensitive=false, [radio, blank()])

# FFmpeg Command
# filter_complex:
#   [0:v] Escalar fondo a 1280x720 (llenar lienzo completo)
#   [2:v] Escalar overlay a 1280x720 (llenar lienzo completo)
#   overlay + drawtext para texto dinámico
# Leer URL de RTMP desde variable de entorno (o usar un valor por defecto)
rtmp_url = environment.get(default="rtmp://transmisor:1935/live/ac7420f3-3c81-40a3-8fe8-c05ece6540b6.stream?token=z3nStream", "RTMP_URL")

ffmpeg_cmd = "ffmpeg -hide_banner -y -stream_loop -1 -i /media/videos/Spring-FullHD1.5_Op.mp4 -thread_queue_size 4096 -i pipe:0 -i /media/imagenes/Untitled_1080.png -filter_complex \"[0:v]scale=1920:1080:flags=fast_bilinear,format=yuv420p[bg];[bg][2:v]overlay=x=0:y=0:format=yuv420:eof_action=repeat[v1];[v1]drawtext=textfile=/tmp/now_playing.txt:reload=1:fontfile=/usr/share/fonts/truetype/custom/MedievalSharp.ttf:fontsize=36:fontcolor=0x251d05:shadowcolor=black:shadowx=2:shadowy=2:x=90:y=250:line_spacing=10[vout]\" -map \"[vout]\" -map 1:a -r 25 -c:v libx264 -preset ultrafast -tune zerolatency -b:v 3000k -maxrate 3000k -bufsize 6000k -g 50 -c:a aac -b:a 192k -f flv #{rtmp_url}"

# Enviar el audio procesado a FFmpeg a través del pipe (stdout de liquidsoap -> stdin de ffmpeg)
output.external(
  %wav,
  ffmpeg_cmd,
  self_sync=true,
  reopen_on_error={true},
  radio
)
