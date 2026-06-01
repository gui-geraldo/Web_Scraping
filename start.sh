#!/usr/bin/env bash
# Sobe o display virtual (Xvfb), o servidor VNC (x11vnc), o noVNC (acesso web)
# e por fim a aplicação. Tudo no mesmo container.
set -e

export DISPLAY=:99
SCREEN_RES="${SCREEN_RES:-1366x768x24}"

echo "[start] Display virtual Xvfb em :99 ($SCREEN_RES)"
Xvfb :99 -screen 0 "$SCREEN_RES" -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
sleep 2

echo "[start] Gerenciador de janelas (fluxbox)"
fluxbox >/tmp/fluxbox.log 2>&1 &
sleep 1

# Servidor VNC anexado ao display :99.
if [ -n "$VNC_PASSWORD" ]; then
  echo "[start] x11vnc COM senha"
  x11vnc -display :99 -forever -shared -rfbport 5900 -passwd "$VNC_PASSWORD" -bg -quiet
else
  echo "[start] x11vnc SEM senha (use apenas na sua rede local!)"
  x11vnc -display :99 -forever -shared -rfbport 5900 -nopw -bg -quiet
fi

echo "[start] noVNC (acesso web) em :6080"
websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/novnc.log 2>&1 &
sleep 1

echo "[start] Aplicação (uvicorn) em :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
