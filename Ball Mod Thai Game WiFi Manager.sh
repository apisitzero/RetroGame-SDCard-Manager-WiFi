#!/bin/bash
# ==============================================================
# Ball Mod Thai Game WiFi Manager v1.1
# High-Speed On-Device Game Manager for R36S / ArkOS Handhelds
# จัดทำโดย: BallModThaiGame & เพจเล่าเรื่องเกม (Lao Reuang Game)
# ==============================================================

export TERM=linux
export PYTHONUNBUFFERED=1
# Free Tier (No license)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/Ball Mod Thai Game WiFi Manager" ]; then
    APP_DIR="$SCRIPT_DIR/Ball Mod Thai Game WiFi Manager"
elif [ -d "$SCRIPT_DIR/ball_mod_thai_game_wifi_manager" ]; then
    APP_DIR="$SCRIPT_DIR/ball_mod_thai_game_wifi_manager"
else
    APP_DIR="$SCRIPT_DIR/arkos_wifi_manager"
fi

# Switch output to terminal framebuffer console on R36S if available
if [ -c "/dev/tty1" ]; then
    exec < /dev/tty1 > /dev/tty1 2>&1
fi

# Clear screen and hide cursor
clear
printf "\033[?25l"

# Ensure cursor is restored and screen cleared upon exit
cleanup() {
    printf "\033[?25h"
    clear
    echo "=============================================="
    echo " รีสตาร์ท EmulationStation เพื่ออัปเดตเกมใหม่..."
    echo "=============================================="
    sudo systemctl restart emulationstation 2>/dev/null || (sudo killall -9 emulationstation 2>/dev/null; sleep 1; sudo emulationstation &)
    exit 0
}
trap cleanup EXIT INT TERM

# Detect Python 3
PY_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
elif [ -x "/usr/bin/python3" ]; then
    PY_BIN="/usr/bin/python3"
elif [ -x "/usr/local/bin/python3" ]; then
    PY_BIN="/usr/local/bin/python3"
fi

if [ -z "$PY_BIN" ]; then
    echo "=============================================="
    echo " Error: Python 3 not found on this ArkOS device!"
    echo "=============================================="
    sleep 5
    exit 1
fi

# Launch RetroGame WiFi Manager Python Server
$PY_BIN "$APP_DIR/server.py"

# Cleanup on normal exit
cleanup
