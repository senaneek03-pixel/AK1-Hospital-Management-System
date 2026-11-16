#!/usr/bin/env bash
# One command to run the app in Codespaces: installs anything missing,
# starts the browser desktop, then opens AK1 Hospital on it.
cd "$(dirname "$0")/.."

if ! /usr/bin/python3 -c "import tkinter" 2>/dev/null || ! command -v Xvfb >/dev/null; then
    echo "Installing Tkinter and the browser desktop (first time only)..."
    bash .devcontainer/setup.sh || exit 1
fi

bash .devcontainer/start-desktop.sh
echo "Opening AK1 Hospital on the desktop (login: admin / admin123)..."
DISPLAY=:1 /usr/bin/python3 ak1_hospital.py
