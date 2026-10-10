# -*- coding: utf-8 -*-
"""
RetroGame & SD Card Manager Version WiFi v1.1 - On-Device HTTP Server
Created for: เพจเล่าเรื่องเกม (Lao Reuang Game) & BallModThaiGame
Author: AntiGravity
Zero-dependency Python 3 HTTP Server with Token Dictionary, RAM Caching & License System
"""

import os
import sys

# Ensure UTF-8 console output
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import json
import socket
import signal
import shutil
import subprocess
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import mimetypes
import secrets
import tempfile
import threading
import time

# Add current directory to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from tui import print_tui
from game_manager import ArkOSGameManager
from license_manager import LicenseManager
from input_listener import ConsoleInputListener
import scraper

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def get_local_ip():
    """Detect LAN IP address of the R36S console."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('1.1.1.1', 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            import subprocess
            out = subprocess.check_output(['hostname', '-I']).decode().strip()
            ip = out.split()[0] if out else '127.0.0.1'
        except Exception:
            ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def parse_multipart_streaming(rfile, content_length, boundary, temp_dir=None):
    """
    Zero-dependency streaming RFC 7578 multipart/form-data parser.
    Streams large ROM and media files directly to disk chunks (64KB buffer)
    to completely prevent RAM MemoryError on RK3326 devices (R36S, R36H).
    """
    boundary_bytes = boundary.encode('ascii') if isinstance(boundary, str) else boundary
    delimiter = b"\r\n--" + boundary_bytes
    initial_boundary = b"--" + boundary_bytes

    remaining = content_length
    buf = bytearray()
    CHUNK_SIZE = 65536

    def read_more():
        nonlocal remaining
        if remaining <= 0:
            return 0
        to_read = min(CHUNK_SIZE, remaining)
        chunk = rfile.read(to_read)
        if not chunk:
            remaining = 0
            return 0
        remaining -= len(chunk)
        buf.extend(chunk)
        return len(chunk)

    # 1. Read past initial boundary
    while initial_boundary not in buf:
        if read_more() == 0:
            break

    init_idx = buf.find(initial_boundary)
    if init_idx == -1:
        return {}
    del buf[:init_idx + len(initial_boundary)]

    # Skip initial CRLF or trailing --
    while len(buf) < 2 and read_more() > 0:
        pass
    if buf.startswith(b"\r\n"):
        del buf[:2]
    elif buf.startswith(b"--"):
        return {}

    fields = {}

    while True:
        # Read headers for this part (until \r\n\r\n)
        while b"\r\n\r\n" not in buf:
            if read_more() == 0:
                break

        hdr_idx = buf.find(b"\r\n\r\n")
        if hdr_idx == -1:
            break

        header_bytes = bytes(buf[:hdr_idx])
        del buf[:hdr_idx + 4]

        header_str = header_bytes.decode('utf-8', errors='ignore')
        name = None
        filename = None
        for line in header_str.split('\r\n'):
            if line.lower().startswith('content-disposition:'):
                for part in line.split(';'):
                    part = part.strip()
                    if part.lower().startswith('name='):
                        name = part.split('=', 1)[1].strip('"\'')
                    elif part.lower().startswith('filename='):
                        filename = part.split('=', 1)[1].strip('"\'')

        if not name:
            name = f"unknown_{len(fields)}"

        # If this part has a filename or is 'file'/'cover_file', stream directly to disk temp file
        is_file_part = bool(filename) or (name in ('file', 'cover_file'))
        delim_len = len(delimiter)

        if is_file_part:
            fd, tmp_path = tempfile.mkstemp(prefix="upload_", dir=temp_dir)
            os.close(fd)
            with open(tmp_path, "wb") as out_f:
                while True:
                    delim_pos = buf.find(delimiter)
                    if delim_pos != -1:
                        out_f.write(buf[:delim_pos])
                        del buf[:delim_pos + delim_len]
                        break
                    else:
                        if len(buf) >= delim_len:
                            safe_len = len(buf) - delim_len + 1
                            out_f.write(buf[:safe_len])
                            del buf[:safe_len]
                        if read_more() == 0:
                            out_f.write(buf)
                            buf.clear()
                            break

            fields[name] = {
                'filename': filename,
                'path': tmp_path,
                'is_file': True
            }
        else:
            val_bytes = bytearray()
            while True:
                delim_pos = buf.find(delimiter)
                if delim_pos != -1:
                    val_bytes.extend(buf[:delim_pos])
                    del buf[:delim_pos + delim_len]
                    break
                else:
                    if len(buf) >= delim_len:
                        safe_len = len(buf) - delim_len + 1
                        val_bytes.extend(buf[:safe_len])
                        del buf[:safe_len]
                    if read_more() == 0:
                        val_bytes.extend(buf)
                        buf.clear()
                        break
            fields[name] = {
                'filename': filename,
                'data': bytes(val_bytes),
                'value': bytes(val_bytes).decode('utf-8', errors='ignore'),
                'is_file': False
            }

        while len(buf) < 2 and read_more() > 0:
            pass
        if buf.startswith(b"--"):
            break
        elif buf.startswith(b"\r\n"):
            del buf[:2]

    # Drain any remaining bytes from rfile to keep socket clean
    while remaining > 0:
        chunk = rfile.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            break
        remaining -= len(chunk)

    return fields

class ArkOSRequestHandler(BaseHTTPRequestHandler):
    server_version = "RetroGame-SDCard-Manager-WiFi/1.1"

    def log_message(self, format, *args):
        # Keep R36S terminal TUI clean
        pass

    def send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        is_premium = self.server.license_mgr.is_premium()

        # 1. Root & Static Files
        if path == '/' or path == '/index.html':
            html_file = os.path.join(CURRENT_DIR, 'web', 'index.html')
            if os.path.exists(html_file):
                with open(html_file, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # Static assets (such as ads: /ads/ad1.png, mascot: /mascot.png, etc.)
        if path == '/mascot.png' or path.startswith('/ads/') or path.startswith('/static/'):
            clean_rel = path.lstrip('/')
            local_path = os.path.join(CURRENT_DIR, 'web', clean_rel)
            if os.path.exists(local_path) and os.path.isfile(local_path):
                mime, _ = mimetypes.guess_type(local_path)
                with open(local_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', mime or 'application/octet-stream')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                self.wfile.write(content)
                return

        # 2. License Info
        if path == '/api/license':
            return self.send_json(self.server.license_mgr.get_license_data())

        # 3. System Status & Storage
        if path == '/api/status':
            disk_info = self.server.game_mgr.get_disk_info()
            resp = {
                "status": "online",
                "version": "1.1",
                "app_name": "RetroGame & SD Card Manager Version WiFi",
                "host": self.server.host_ip,
                "port": self.server.server_port,
                "disk": disk_info,
                "root": self.server.game_mgr.roms_root,
                "license": self.server.license_mgr.get_license_data(),
                "pin_required": bool(self.server.pin),
                "brand": "เพจเล่าเรื่องเกม (Lao Reuang Game)",
                "banner_title": "BallModThaiGame"
            }
            return self.send_json(resp)

        # 4. Gaming Systems (Hides 0-game folders by default, sorts by game count)
        if path == '/api/systems':
            include_empty = query.get('all', ['false'])[0].lower() == 'true'
            systems = self.server.game_mgr.list_systems(is_premium=is_premium, include_empty=include_empty)
            return self.send_json(systems)

        # 5. List Games (Filtered if Free)
        if path == '/api/games':
            system_id = query.get('system', [''])[0]
            if not system_id:
                return self.send_json({"error": "Missing system parameter"}, 400)
            refresh = query.get('refresh', ['false'])[0].lower() == 'true'
            games = self.server.game_mgr.list_games(system_id, force_refresh=refresh, is_premium=is_premium)
            return self.send_json({"system": system_id, "games": games, "count": len(games)})

        # 6. High-Speed Image Server (Token or Path with aggressive Browser Caching)
        if path == '/api/image':
            token = query.get('token', [''])[0]
            img_path = None

            if token:
                game = self.server.game_mgr.get_game_by_token(token)
                if game and game.get("cover_abs_path") and os.path.exists(game["cover_abs_path"]):
                    img_path = game["cover_abs_path"]
            else:
                system_id = query.get('system', [''])[0]
                rel_path = query.get('path', [''])[0]
                if system_id and rel_path:
                    clean_rel = rel_path.lstrip('./').lstrip('/')
                    cand = os.path.join(self.server.game_mgr.roms_root, system_id, clean_rel)
                    if os.path.exists(cand):
                        img_path = cand

            if not img_path or not os.path.exists(img_path):
                self.send_response(404)
                self.end_headers()
                return

            stat = os.stat(img_path)
            etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
            if_none_match = self.headers.get('If-None-Match')
            if if_none_match and if_none_match == etag:
                self.send_response(304)
                self.end_headers()
                return

            ext = os.path.splitext(img_path)[1].lower()
            mime = "image/png"
            if ext in ('.jpg', '.jpeg'):
                mime = "image/jpeg"
            elif ext == '.webp':
                mime = "image/webp"

            try:
                with open(img_path, 'rb') as f:
                    content = f.read()

                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(content)))
                self.send_header('ETag', etag)
                self.send_header('Cache-Control', 'public, max-age=86400, must-revalidate')
                self.end_headers()
                self.wfile.write(content)
            except Exception:
                self.send_response(500)
                self.end_headers()
            return

        # 7. Download ROM (All Tiers)
        if path == '/api/download_rom':
            token = query.get('token', [''])[0]
            game = self.server.game_mgr.get_game_by_token(token)
            if not game or not os.path.exists(game["rom_abs_path"]):
                return self.send_json({"error": "ROM not found"}, 404)

            if game["is_dir"]:
                import zipfile, io
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                    for root, _, files in os.walk(game["rom_abs_path"]):
                        for file in files:
                            full_p = os.path.join(root, file)
                            arcname = os.path.relpath(full_p, game["rom_abs_path"])
                            z.write(full_p, arcname)
                buf.seek(0)
                content = buf.read()
                filename = f"{game['filename']}.zip"
            else:
                with open(game["rom_abs_path"], 'rb') as f:
                    content = f.read()
                filename = game["filename"]

            safe_filename = urllib.parse.quote(filename)
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition', f'attachment; filename="{safe_filename}"; filename*=UTF-8\'\'{safe_filename}')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # ================= Save Manager Endpoints (Premium Only) =================
        if path == '/api/saves':
            if not is_premium:
                return self.send_json({"error": "Save Manager requires Premium membership"}, 403)
            saves = self.server.game_mgr.list_all_saves()
            return self.send_json({"saves": saves, "count": len(saves)})

        if path == '/api/download_save':
            if not is_premium:
                return self.send_json({"error": "Downloading saves requires Premium membership"}, 403)
            token = query.get('token', [''])[0]
            game = self.server.game_mgr.get_game_by_token(token)
            if not game or not game.get("save_abs_path") or not os.path.exists(game["save_abs_path"]):
                return self.send_json({"error": "Save file not found"}, 404)

            with open(game["save_abs_path"], 'rb') as f:
                content = f.read()
            filename = game["save_filename"]
            safe_filename = urllib.parse.quote(filename)
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition', f'attachment; filename="{safe_filename}"; filename*=UTF-8\'\'{safe_filename}')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == '/api/backup_all_saves':
            if not is_premium:
                return self.send_json({"error": "Full Save Backup requires Premium membership"}, 403)
            zip_bytes, count = self.server.game_mgr.backup_all_saves_zip()
            timestamp = secrets.token_hex(4)
            filename = f"All_RetroGame_Saves_{timestamp}.zip"
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Content-Length', str(len(zip_bytes)))
            self.end_headers()
            self.wfile.write(zip_bytes)
            return

        # ================= Cheat Manager Endpoints (Premium Only) =================
        if path == '/api/cheats':
            if not is_premium:
                return self.send_json({"error": "Cheat Manager requires Premium membership"}, 403)
            token = query.get('token', [''])[0]
            if not token:
                return self.send_json({"error": "Missing token"}, 400)
            res = self.server.game_mgr.get_cheats_for_game(token)
            return self.send_json(res)

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get('Content-Length', 0))
        content_type = self.headers.get('Content-Type', '')
        # 0. Clean Shutdown Endpoint (All Tiers)
        if path == '/api/shutdown':
            self.send_json({"success": True, "message": "Server is shutting down. Returning to ArkOS..."})
            def delayed_exit():
                time.sleep(0.5)
                sys.stdout.write("\033[?25h\033[2J\033[H")
                sys.stdout.flush()
                print("\n========================================================================")
                print(" [RetroGame Manager] Web Exit requested. Returning to ArkOS...")
                print("========================================================================")
                sys.stdout.flush()
                os._exit(0)
            threading.Thread(target=delayed_exit, daemon=True).start()
            return

        # 0.1 Instant Handheld Screen Refresh (Restart EmulationStation on ArkOS)
        if path == '/api/restart_es':
            def do_restart_es():
                time.sleep(0.3)
                cmd = "sudo systemctl restart emulationstation 2>/dev/null || (sudo killall -9 emulationstation 2>/dev/null; sleep 1; sudo emulationstation &)"
                try:
                    subprocess.run(cmd, shell=True, timeout=8)
                except Exception as ex:
                    print(f"[Server] restart_es command error: {ex}")

            threading.Thread(target=do_restart_es, daemon=True).start()
            self.send_json({
                "success": True,
                "message": "สั่งรีเฟรชหน้าจอเครื่องเกม R36S แล้ว! หน้ารวมเกมจะรีสตาร์ทเพื่อแสดงเกมและปกใหม่ทันที"
            })
            return

        is_premium = self.server.license_mgr.is_premium()

        # 1. Rename Game via Token (All Tiers)
        if path == '/api/rename':
            raw_body = self.rfile.read(content_length)
            try:
                data = json.loads(raw_body.decode('utf-8'))
                token = data.get('token')
                new_name = data.get('new_name')
                if not token or not new_name:
                    return self.send_json({"success": False, "error": "Missing token or new_name"}, 400)
                res = self.server.game_mgr.rename_game(token, new_name)
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"success": False, "error": str(e)}, 500)

        # 2. Upload Cover Image via Token (All Tiers)
        if path == '/api/upload_cover':
            if 'multipart/form-data' not in content_type:
                return self.send_json({"success": False, "error": "Expected multipart/form-data"}, 400)
            boundary = content_type.split("boundary=")[1].strip()
            temp_upload_dir = os.path.join(self.server.game_mgr.roms_root, ".tmp_uploads")
            os.makedirs(temp_upload_dir, exist_ok=True)
            parts = parse_multipart_streaming(self.rfile, content_length, boundary, temp_dir=temp_upload_dir)

            token = parts.get('token', {}).get('value', '').strip()
            file_part = parts.get('file')
            if not token or not file_part or not file_part.get('path'):
                return self.send_json({"success": False, "error": "Missing token or file"}, 400)

            orig_filename = file_part.get('filename') or 'cover.png'
            ext = os.path.splitext(orig_filename)[1].lower() or '.png'
            cover_path = file_part['path']
            try:
                with open(cover_path, 'rb') as f:
                    img_bytes = f.read()
                res = self.server.game_mgr.apply_cover(token, img_bytes, filename_ext=ext)
                return self.send_json(res)
            finally:
                if os.path.exists(cover_path):
                    try:
                        os.remove(cover_path)
                    except Exception:
                        pass

        # 3. Delete Game via Token (All Tiers)
        if path == '/api/delete':
            raw_body = self.rfile.read(content_length)
            try:
                data = json.loads(raw_body.decode('utf-8'))
                token = data.get('token')
                if not token:
                    return self.send_json({"success": False, "error": "Missing token"}, 400)
                res = self.server.game_mgr.delete_game(token)
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"success": False, "error": str(e)}, 500)

        # 4. Upload ROM File (Streaming chunked upload, PS1 folder support, All Tiers)
        if path == '/api/upload_rom':
            if 'multipart/form-data' not in content_type:
                return self.send_json({"success": False, "error": "Expected multipart/form-data"}, 400)
            boundary = content_type.split("boundary=")[1].strip()
            
            # Temporary upload directory on SD card partition to prevent tmpfs RAM exhaustion
            temp_upload_dir = os.path.join(self.server.game_mgr.roms_root, ".tmp_uploads")
            os.makedirs(temp_upload_dir, exist_ok=True)

            parts = parse_multipart_streaming(self.rfile, content_length, boundary, temp_dir=temp_upload_dir)

            system_id = parts.get('system', {}).get('value', '').strip()
            display_name = parts.get('display_name', {}).get('value', '').strip()
            is_folder = parts.get('is_folder', {}).get('value', '').strip().lower() == 'true'
            folder_name = parts.get('folder_name', {}).get('value', '').strip()
            file_part = parts.get('file')

            if not file_part or not file_part.get('filename') or not file_part.get('path'):
                return self.send_json({"success": False, "error": "No ROM file provided"}, 400)

            filename = file_part['filename']
            rom_temp_path = file_part['path']

            if not system_id or system_id == 'auto':
                ext = os.path.splitext(filename)[1].lower()
                auto_map = {
                    '.gba': 'gba', '.gb': 'gb', '.gbc': 'gbc', '.nes': 'nes',
                    '.sfc': 'sfc', '.smc': 'sfc', '.nds': 'nds', '.n64': 'n64',
                    '.iso': 'psx', '.cue': 'psx', '.chd': 'psx', '.pbp': 'psx',
                    '.md': 'megadrive', '.gen': 'megadrive'
                }
                system_id = auto_map.get(ext, 'gba')

            # Cover support: check if cover_file or cover_url was provided
            cover_part = parts.get('cover_file')
            cover_url = parts.get('cover_url', {}).get('value', '').strip()
            cover_bytes = None
            cover_ext = ".png"

            if cover_part and cover_part.get('path') and os.path.exists(cover_part['path']):
                try:
                    with open(cover_part['path'], 'rb') as cf:
                        cover_bytes = cf.read()
                    if cover_part.get('filename'):
                        cover_ext = os.path.splitext(cover_part['filename'])[1].lower() or ".png"
                finally:
                    try:
                        os.remove(cover_part['path'])
                    except Exception:
                        pass
            elif cover_url:
                try:
                    cover_bytes = scraper.download_image_bytes(cover_url)
                except Exception:
                    cover_bytes = None

            try:
                res = self.server.game_mgr.save_uploaded_rom(
                    system_id, filename,
                    display_name=display_name, is_folder=is_folder, folder_name=folder_name,
                    cover_bytes=cover_bytes, cover_ext=cover_ext,
                    temp_file_path=rom_temp_path
                )
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"success": False, "error": str(e)}, 500)
            finally:
                if rom_temp_path and os.path.exists(rom_temp_path):
                    try:
                        os.remove(rom_temp_path)
                    except Exception:
                        pass

        # 5. Search Libretro Covers (All Tiers)
        if path == '/api/search_covers':
            raw_body = self.rfile.read(content_length)
            try:
                data = json.loads(raw_body.decode('utf-8'))
                query = data.get('query', '')
                system_id = data.get('system', '')
                results = scraper.search_box_arts(query, system_id)
                return self.send_json({"results": results})
            except Exception as e:
                return self.send_json({"results": [], "error": str(e)})

        # 6. Apply Online Cover directly to Token (All Tiers)
        if path == '/api/apply_cover':
            raw_body = self.rfile.read(content_length)
            try:
                data = json.loads(raw_body.decode('utf-8'))
                token = data.get('token')
                image_url = data.get('image_url')
                if not token or not image_url:
                    return self.send_json({"success": False, "error": "Missing token or image_url"}, 400)
                img_bytes = scraper.download_image_bytes(image_url)
                res = self.server.game_mgr.apply_cover(token, img_bytes, filename_ext=".png")
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"success": False, "error": str(e)}, 500)

        # ================= Save Manager POST Endpoints (Premium Only) =================
        if path == '/api/delete_save':
            if not is_premium:
                return self.send_json({"success": False, "error": "Save Manager requires Premium membership"}, 403)
            raw_body = self.rfile.read(content_length)
            try:
                data = json.loads(raw_body.decode('utf-8'))
                system_id = data.get('system')
                filename = data.get('filename')
                if not system_id or not filename:
                    return self.send_json({"success": False, "error": "Missing system or filename"}, 400)
                res = self.server.game_mgr.delete_save_file(system_id, filename)
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"success": False, "error": str(e)}, 500)

        # ================= Cheat Manager POST Endpoints (Premium Only) =================
        if path == '/api/save_cheats':
            if not is_premium:
                return self.send_json({"success": False, "error": "Cheat Manager requires Premium membership"}, 403)
            raw_body = self.rfile.read(content_length)
            try:
                data = json.loads(raw_body.decode('utf-8'))
                token = data.get('token')
                cheats = data.get('cheats', [])
                if not token:
                    return self.send_json({"success": False, "error": "Missing token"}, 400)
                res = self.server.game_mgr.save_cheats_for_game(token, cheats)
                return self.send_json(res)
            except Exception as e:
                return self.send_json({"success": False, "error": str(e)}, 500)

        if path == '/api/upload_cheat_zip':
            if not is_premium:
                return self.send_json({"success": False, "error": "Cheat Manager requires Premium membership"}, 403)
            if 'multipart/form-data' not in content_type:
                return self.send_json({"success": False, "error": "Expected multipart/form-data"}, 400)
            boundary = content_type.split("boundary=")[1].strip()
            body_bytes = self.rfile.read(content_length)
            parts = parse_multipart(body_bytes, boundary)
            file_part = parts.get('file')
            if not file_part:
                return self.send_json({"success": False, "error": "No file provided"}, 400)
            res = self.server.game_mgr.upload_cheat_zip(file_part['data'])
            return self.send_json(res)

        self.send_response(404)
        self.end_headers()

def main():
    config_file = os.path.join(CURRENT_DIR, "config.json")
    port = 8080
    custom_roms = None
    pin = None

    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                port = cfg.get("port", port)
                custom_roms = cfg.get("roms_path", custom_roms)
                pin = cfg.get("pin", pin)
        except Exception:
            pass

    host_ip = get_local_ip()
    session_token = secrets.token_hex(16)

    # Initialize Managers
    license_mgr = LicenseManager(CURRENT_DIR)
    game_mgr = ArkOSGameManager(custom_roms)

    # Start Threaded Server
    server = ThreadedHTTPServer(('0.0.0.0', port), ArkOSRequestHandler)
    server.game_mgr = game_mgr
    server.license_mgr = license_mgr
    server.host_ip = host_ip
    server.pin = pin
    server.session_token = session_token

    # Display TUI Screen on R36S Console
    print_tui(host_ip, port, license_info=license_mgr.get_license_data(), pin=pin)

    def request_shutdown(reason="Gamepad Button"):
        sys.stdout.write("\033[?25h\033[2J\033[H")
        sys.stdout.flush()
        print("\n========================================================================")
        print(f" [RetroGame Manager v1.1] Exit triggered: {reason}")
        print(" Returning to ArkOS EmulationStation...")
        print("========================================================================")
        sys.stdout.flush()
        os._exit(0)

    # Start Console Gamepad & Keyboard Input Listener
    input_listener = ConsoleInputListener(on_exit_callback=request_shutdown)
    input_listener.start()

    signal.signal(signal.SIGINT, lambda s, f: request_shutdown("SIGINT (Ctrl+C)"))
    signal.signal(signal.SIGTERM, lambda s, f: request_shutdown("SIGTERM"))

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        request_shutdown("KeyboardInterrupt")

if __name__ == "__main__":
    main()
