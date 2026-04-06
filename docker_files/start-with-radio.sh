#!/bin/bash
# Script de inicio optimizado para Ubuntu 24.04 (Radio + VNC)

# 1. Preparación del Entorno
export DISPLAY=:1
export HOME=/headless
export XDG_RUNTIME_DIR=/tmp/runtime-vncuser
export LIBGL_ALWAYS_SOFTWARE=1
export QT_X11_NO_MITSHM=1
export QT_QUICK_BACKEND=software
export CEF_USE_SOFTWARE_RENDERING=1
export QT_XCB_GL_INTEGRATION=none
export QT_NO_GLIB=1
export OBS_BROWSER_NOSANDBOX=1
mkdir -p $XDG_RUNTIME_DIR && chmod 700 $XDG_RUNTIME_DIR

# Limpieza de bloqueos (OBS, VNC, X11)
rm -rf $HOME/.config/obs-studio/plugin_config/obs-browser/Singleton* /tmp/.X1-lock /tmp/.X11-unix/X1 2>/dev/null || true

# 2. Configurar OBS WebSocket (Forzar habilitación)
mkdir -p $HOME/.config/obs-studio
GLOBAL_INI="$HOME/.config/obs-studio/global.ini"
WS_JSON="$HOME/.config/obs-studio/plugin_config/obs-websocket/config.json"
if [ ! -f "$GLOBAL_INI" ]; then
    echo "[OBSWebSocket]" > "$GLOBAL_INI"
fi
# Usar Python para asegurar que el WebSocket esté activo en ambos formatos (global.ini + config.json)
python3 -c '
import re, os, json

# --- global.ini (formato legacy) ---
path = os.path.expanduser("~/.config/obs-studio/global.ini")
if not os.path.exists(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: f.write("[OBSWebSocket]\n")
with open(path, "r") as f: content = f.read()
if "[OBSWebSocket]" not in content: content += "\n[OBSWebSocket]\n"
for k, v in [("ServerEnabled", "true"), ("ServerPort", "4455"), ("AuthRequired", "true")]:
    pat_lower = re.compile(rf"\n{k.lower()}\s*=.*", re.IGNORECASE)
    pat_exact = re.compile(rf"\n{k}=.*")
    if pat_exact.search(content):
        content = pat_exact.sub(f"\n{k}={v}", content)
    elif pat_lower.search(content):
        content = pat_lower.sub(f"\n{k}={v}", content)
    else:
        content = content.replace("[OBSWebSocket]", f"[OBSWebSocket]\n{k}={v}")
with open(path, "w") as f: f.write(content)

# --- config.json (OBS 32+) ---
jpath = os.path.expanduser("~/.config/obs-studio/plugin_config/obs-websocket/config.json")
if os.path.exists(jpath):
    try:
        with open(jpath, "r") as f: data = json.load(f)
        data["auth_required"] = True
        data["server_enabled"] = True
        data["server_port"] = 4455
        with open(jpath, "w") as f: json.dump(data, f, indent=2)
    except: pass
'
echo "🔍 Diagnóstico OBS: $(grep 'ServerEnabled' $GLOBAL_INI || echo 'No encontrado')"
# Ver puerto 4455 (espero que OBS lo abra pronto)
(sleep 15; echo "🔌 Escaneando puerto 4455:"; netstat -tln | grep 4455 || echo "❌ Puerto 4455 no abierto aún") &

# 3. Configurar resolución y password de VNC VNC_COL_DEPTH=24/.vnc
mkdir -p $HOME/.vnc
echo "${VNC_PW:-vncpass}" | vncpasswd -f > $HOME/.vnc/passwd
chmod 600 $HOME/.vnc/passwd

# 3. Iniciar Servicios de Red (noVNC)
echo "🌐 Iniciando noVNC..."
websockify --web /usr/share/novnc/ 6080 localhost:5901 > $STARTUPDIR/no_vnc_startup.log 2>&1 &

# 4. Iniciar Servidor Gráfico (TigerVNC)
echo "🖥️ Iniciando VNC Server ($VNC_RESOLUTION)..."
vncserver -kill :1 2>/dev/null || true
vncserver :1 -depth $VNC_COL_DEPTH -geometry $VNC_RESOLUTION -localhost no >> $STARTUPDIR/vnc_startup.log 2>&1

# 4. Iniciar Controlador Python (Auto Media Player) en segundo plano
echo "🐍 Iniciando Controlador Python..."
( sleep 2; cd /app && python3 app.py ) &

# 6. Lanzar OBS Studio (esperando al Servidor X)
(
  while ! xdpyinfo -display $DISPLAY >/dev/null 2>&1; do sleep 1; done
  
  echo "🎥 X11 detectado. Lanzando OBS..."
  
  # Whitelist de Navegador y configuración de seguridad
  WL="MAP * 127.0.0.1, EXCLUDE localhost, EXCLUDE 127.0.0.1, EXCLUDE *.youtube.com, EXCLUDE youtube.com, EXCLUDE *.twitch.tv, EXCLUDE twitch.tv, EXCLUDE *.kick.com, EXCLUDE kick.com, EXCLUDE *.tiktok.com, EXCLUDE tiktok.com"
  export OBS_BROWSER_EXTRA_FLAGS="--password-store=basic --disable-features=Libsecret --disable-gpu-sandbox --autoplay-policy=no-user-gesture-required --host-rules=\"$WL\""

  # Neutralizar Llaveros (Keyrings)
  export GNOME_KEYRING_CONTROL=
  export SSH_AUTH_SOCK=
  killall -9 gnome-keyring-daemon 2>/dev/null || true
  rm -rf "$HOME/.local/share/keyrings" && mkdir -p "$HOME/.local/share/keyrings"
  echo -n "login" > "$HOME/.local/share/keyrings/default"

  # Opciones de lanzamiento OBS (Las banderas del navegador ya están en OBS_BROWSER_EXTRA_FLAGS)
  OPTS="--disable-shutdown-check"
  
  if [ "$AUTO_STREAM" = "true" ]; then
    obs $OPTS --startstreaming
  else
    obs $OPTS
  fi
) &

# 7. Mantener contenedor activo (Logs)
echo "✅ Entorno VNC activo. Conexión vía: http://[IP]:6901/vnc.html"
tail -F $STARTUPDIR/*.log $HOME/.vnc/*$DISPLAY.log
