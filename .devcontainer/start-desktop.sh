#!/usr/bin/env bash
# Starts the virtual desktop: a screen (Xvfb :1), a window manager (fluxbox),
# a VNC server (x11vnc) and the browser viewer (noVNC) on port 6080.
export DISPLAY=:1

start() {
    local name=$1
    shift
    if ! pgrep -x "$name" >/dev/null; then
        setsid -f "$@" >"/tmp/$name.log" 2>&1
    fi
}

start Xvfb Xvfb :1 -screen 0 1600x900x24
sleep 2
start fluxbox fluxbox
start x11vnc x11vnc -display :1 -forever -shared -nopw -rfbport 5901 -quiet
start websockify websockify --web /usr/share/novnc 6080 localhost:5901
sleep 1
echo "Desktop is running. Open port 6080 (Ports tab) and click Connect."
