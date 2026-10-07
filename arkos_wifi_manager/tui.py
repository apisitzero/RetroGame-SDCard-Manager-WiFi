# -*- coding: utf-8 -*-
"""
TUI Display for RetroGame & SD Card Manager Version WiFi v1.1
Crafted for: เพจเล่าเรื่องเกม (Lao Reuang Game) & BallModThaiGame
Terminal resolution: 640x480 on ArkOS handhelds (R36S, RGB20S, RG351/353)
"""

import sys

RESET   = "\033[0m"
BOLD    = "\033[1m"
GREEN   = "\033[1;32m"
CYAN    = "\033[1;36m"
YELLOW  = "\033[1;33m"
WHITE   = "\033[1;37m"
MAGENTA = "\033[1;35m"
GRAY    = "\033[90m"
GOLD    = "\033[38;5;220m"

# ASCII Art Logo for 'BallModThaiGame' (English only, safe for Linux consoles)
ASCII_BALL_MOD = [
    r"   ___       _ _ __  __          _ _____ _           _  ___       ",
    r"  | _ ) __ _| | |  \/  |___  __| |_   _| |_  __ _ (_)/ __|__ _ _ _ __  ___ ",
    r"  | _ \/ _` | | | |\/| / _ \/ _` | | | | ' \/ _` || | (_ / _` | '  \/ -_)",
    r"  |___/\__,_|_|_|_|  |_\___/\__,_| |_| |_||_\__,_|/_|\___\__,_|_|_|_\___|",
    r"          * * *  B A L L   M O D   T H A I   G A M E  * * *       "
]

def render_tui(ip: str, port: int, license_info: dict = None, pin: str = None) -> str:
    """Renders the terminal user interface tailored for R36S 640x480 screen."""
    lic = license_info or {}
    is_premium = lic.get("is_premium", False)
    mac = lic.get("device_mac", "N/A")
    days_left = lic.get("days_left", 0)
    expires_at = lic.get("expires_at", "N/A")
    customer = lic.get("customer", "")

    lines = []
    lines.append("\033[2J\033[H")  # Clear screen and move cursor to (0,0)
    lines.append(f"{CYAN}========================================================================{RESET}")
    lines.append(f"{YELLOW}{BOLD}          * * *   P A G E :  L A O   R E U A N G   G A M E   * * *      {RESET}")
    lines.append(f"{CYAN}========================================================================{RESET}")

    # Print ASCII Art Logo 'BallModThaiGame'
    for b_line in ASCII_BALL_MOD:
        lines.append(f"{MAGENTA}{b_line}{RESET}")

    lines.append(f"{CYAN}------------------------------------------------------------------------{RESET}")

    if is_premium:
        lines.append(f" Status:  {GREEN}[ ONLINE: PREMIUM ACTIVE ]{RESET}     {GRAY}Res: 640x480 (ArkOS){RESET}")
        lines.append(f" Expiry:  {YELLOW}{BOLD}{expires_at}{RESET} ({days_left} days left) | Member: {WHITE}{customer}{RESET}")
    else:
        lines.append(f" Status:  {GREEN}[ ONLINE: FREE TIER ]{RESET}          {GRAY}Res: 640x480 (ArkOS){RESET}")

    lines.append(f" MAC:     {WHITE}{BOLD}{mac}{RESET}")
    lines.append(f" Address: {WHITE}{BOLD}http://{ip}:{port}{RESET}")
    if pin:
        lines.append(f" PIN:     {YELLOW}{BOLD}{pin}{RESET}  (Quick Access PIN)")

    lines.append(f"{CYAN}------------------------------------------------------------------------{RESET}")
    lines.append(f"{WHITE}{BOLD} Instructions:{RESET}")
    lines.append(f"  {CYAN}1.{RESET} Open a browser and enter the IP address shown above.")
    lines.append(f"  {CYAN}2.{RESET} Once connected, manage your games from the web page.")
    lines.append(f"  {CYAN}3.{RESET} To stop, close this terminal; the browser link will end too.")
    lines.append(f"{CYAN}========================================================================{RESET}")
    lines.append(f"{GRAY} Web Server is running on R36S. Press [Ctrl+C] or [B] button to exit{RESET}")
    return "\n".join(lines)

def print_tui(ip: str, port: int, license_info: dict = None, pin: str = None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(render_tui(ip, port, license_info, pin), flush=True)

if __name__ == "__main__":
    demo_lic = {
        "is_premium": True,
        "device_mac": "E0:0A:F6:BC:D1:BE",
        "days_left": 28,
        "expires_at": "2026-11-06",
        "customer": "Somchai Tester"
    }
    print_tui("192.168.1.188", 8080, demo_lic)
