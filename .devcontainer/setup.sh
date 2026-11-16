#!/usr/bin/env bash
# Installs Python's Tkinter and a small virtual desktop that the browser can show (noVNC).
set -e
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    python3 python3-tk xvfb x11vnc fluxbox novnc websockify fonts-dejavu-core procps
# Opening port 6080 then shows the noVNC viewer straight away.
sudo ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html
echo "Setup finished. Start the app with: bash .devcontainer/run-app.sh"
