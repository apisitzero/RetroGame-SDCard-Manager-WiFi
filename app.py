import os
import json
import io
import mimetypes
import hashlib
from flask import Flask, render_template, request, jsonify, send_file, Response
from sftp_client import ArkOSManager, SYSTEM_METADATA
from scraper import search_box_arts, download_image_bytes

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024  # 4GB max upload size (supports large PS1/PSP ISOs)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache_images")
os.makedirs(CACHE_DIR, exist_ok=True)

# Global manager instance
manager: ArkOSManager = None

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "host": "192.168.1.",
        "port": 22,
        "username": "ark",
        "password": "ark",
        "roms_root": "auto"
    }

def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Save config error:", e)

# Pre-load config
initial_cfg = load_config()
if initial_cfg.get("host") and initial_cfg["host"] != "192.168.1.":
    manager = ArkOSManager(
        host=initial_cfg["host"],
        port=initial_cfg.get("port", 22),
        username=initial_cfg.get("username", "ark"),
        password=initial_cfg.get("password", "ark"),
        roms_root=initial_cfg.get("roms_root", "auto")
    )

def get_manager():
    global manager
    if manager and manager.is_connected():
        return manager
    cfg = load_config()
    if cfg.get("host") and cfg["host"] != "192.168.1.":
        m = ArkOSManager(
            host=cfg["host"],
            port=int(cfg.get("port", 22)),
            username=cfg.get("username", "ark"),
            password=cfg.get("password", "ark"),
            roms_root=cfg.get("roms_root", "auto")
        )
        ok, _ = m.connect()
        if ok:
            manager = m
            return manager
    return manager

@app.route('/')
def index():
    cfg = load_config()
    return render_template('index.html', config=cfg)

@app.route('/api/connect', methods=['POST'])
def api_connect():
    global manager
    data = request.json or {}
    host = data.get('host', '').strip()
    port = int(data.get('port', 22))
    username = data.get('username', 'ark').strip()
    password = data.get('password', 'ark')
    roms_root = data.get('roms_root', 'auto').strip()

    if not host:
        return jsonify({"success": False, "error": "กรุณาระบุ IP Address ของเครื่อง ArkOS"}), 400

    new_manager = ArkOSManager(host=host, port=port, username=username, password=password, roms_root=roms_root)
    success, msg = new_manager.connect()

    if success:
        manager = new_manager
        save_config({
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "roms_root": roms_root
        })
        disk_info = manager.get_disk_usage()
        return jsonify({
            "success": True,
            "message": msg,
            "disk": disk_info,
            "root": manager.detected_root
        })
    else:
        return jsonify({"success": False, "error": msg}), 400

@app.route('/api/status', methods=['GET'])
def api_status():
    mgr = get_manager()
    if mgr and mgr.is_connected():
        disk = mgr.get_disk_usage()
        return jsonify({
            "connected": True,
            "host": mgr.host,
            "root": mgr.detected_root,
            "disk": disk
        })
    return jsonify({"connected": False, "config": load_config()})

@app.route('/api/disconnect', methods=['POST'])
def api_disconnect():
    global manager
    if manager:
        manager.close()
    return jsonify({"success": True})

@app.route('/api/systems', methods=['GET'])
def api_systems():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400
    systems = mgr.list_systems()
    return jsonify({"systems": systems})

@app.route('/api/games', methods=['GET'])
def api_games():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400
    system_id = request.args.get('system', '').strip()
    if not system_id:
        return jsonify({"error": "กรุณาระบุระบบเกม (system)"}), 400

    games = mgr.list_games(system_id)
    return jsonify({"games": games, "system": system_id})

@app.route('/api/image', methods=['GET'])
def api_image():
    system_id = request.args.get('system', '').strip()
    cover_path = request.args.get('path', '').strip()
    mgr = get_manager()
    if not system_id or not cover_path or not mgr:
        return Response(status=404)

    # Cache key
    cache_key = hashlib.md5(f"{mgr.host}_{system_id}_{cover_path}".encode('utf-8')).hexdigest()
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.png")

    if os.path.exists(cache_file):
        return send_file(cache_file, mimetype='image/png')

    img_data = mgr.get_image_bytes(system_id, cover_path)
    if img_data:
        try:
            with open(cache_file, 'wb') as f:
                f.write(img_data)
        except Exception:
            pass
        return send_file(io.BytesIO(img_data), mimetype='image/png')

    return Response(status=404)

@app.route('/api/upload_rom', methods=['POST'])
def api_upload_rom():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400

    if 'file' not in request.files:
        return jsonify({"error": "ไม่พบไฟล์เกมที่ส่งมา"}), 400

    file = request.files['file']
    filename = file.filename
    if not filename:
        return jsonify({"error": "ชื่อไฟล์ไม่ถูกต้อง"}), 400

    system_id = request.form.get('system', '').strip()
    display_name = request.form.get('display_name', '').strip()

    # If system is not specified, auto-detect by file extension
    if not system_id or system_id == 'auto':
        ext = os.path.splitext(filename)[1].lower()
        matched_sys = None
        for sys_k, meta in SYSTEM_METADATA.items():
            if ext in meta['exts']:
                matched_sys = sys_k
                break
        system_id = matched_sys or 'gba'

    try:
        success = mgr.upload_rom_file(system_id, filename, file.stream, display_name=display_name or None)
        if success:
            return jsonify({"success": True, "filename": filename, "system": system_id})
        else:
            return jsonify({"error": "การอัปโหลดล้มเหลว"}), 500
    except Exception as e:
        return jsonify({"error": f"เกิดข้อผิดพลาดในการอัปโหลด: {str(e)}"}), 500

@app.route('/api/upload_cover', methods=['POST'])
def api_upload_cover():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400

    if 'image' not in request.files:
        return jsonify({"error": "ไม่พบไฟล์รูปภาพปก"}), 400

    system_id = request.form.get('system', '').strip()
    rom_filename = request.form.get('rom_filename', '').strip()

    if not system_id or not rom_filename:
        return jsonify({"error": "ข้อมูลระบบหรือไฟล์เกมไม่ครบถ้วน"}), 400

    img_file = request.files['image']
    img_bytes = img_file.read()
    ext = os.path.splitext(img_file.filename)[1].lower() or '.png'

    try:
        rel_path = mgr.upload_cover_file(system_id, rom_filename, img_bytes, img_extension=ext)
        # Clear cache for this image
        cache_key = hashlib.md5(f"{mgr.host}_{system_id}_{rel_path}".encode('utf-8')).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.png")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
            except Exception:
                pass
        return jsonify({"success": True, "cover_path": rel_path})
    except Exception as e:
        return jsonify({"error": f"อัปโหลดปกไม่สำเร็จ: {str(e)}"}), 500

@app.route('/api/search_covers', methods=['POST'])
def api_search_covers():
    data = request.json or {}
    query = data.get('query', '').strip()
    system_id = data.get('system', '').strip()

    if not query:
        return jsonify({"error": "กรุณาระบุชื่อเกมที่ต้องการค้นหา"}), 400

    results = search_box_arts(query, system_id)
    return jsonify({"results": results})

@app.route('/api/apply_online_cover', methods=['POST'])
def api_apply_online_cover():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400

    data = request.json or {}
    image_url = data.get('image_url', '').strip()
    system_id = data.get('system', '').strip()
    rom_filename = data.get('rom_filename', '').strip()

    if not image_url or not system_id or not rom_filename:
        return jsonify({"error": "ข้อมูลไม่ครบถ้วน"}), 400

    try:
        img_bytes = download_image_bytes(image_url)
        rel_path = mgr.upload_cover_file(system_id, rom_filename, img_bytes, img_extension='.png')
        # Clear cache
        cache_key = hashlib.md5(f"{mgr.host}_{system_id}_{rel_path}".encode('utf-8')).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.png")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
            except Exception:
                pass
        return jsonify({"success": True, "cover_path": rel_path})
    except Exception as e:
        return jsonify({"error": f"ดาวน์โหลดหรือติดตั้งปกไม่สำเร็จ: {str(e)}"}), 500

@app.route('/api/rename_game', methods=['POST'])
def api_rename_game():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400

    data = request.json or {}
    system_id = data.get('system', '').strip()
    old_filename = data.get('old_filename', '').strip()
    new_display_name = data.get('new_display_name', '').strip()
    rename_rom_file = bool(data.get('rename_rom_file', False))
    new_filename = data.get('new_filename', '').strip()

    if not system_id or not old_filename or not new_display_name:
        return jsonify({"error": "ข้อมูลไม่ครบถ้วน"}), 400

    success, msg = mgr.rename_game(
        system_id=system_id,
        old_filename=old_filename,
        new_display_name=new_display_name,
        rename_rom_file=rename_rom_file,
        new_filename=new_filename if rename_rom_file else None
    )

    if success:
        return jsonify({"success": True, "message": msg})
    return jsonify({"error": msg}), 400

@app.route('/api/delete_game', methods=['POST'])
def api_delete_game():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400

    data = request.json or {}
    system_id = data.get('system', '').strip()
    filename = data.get('filename', '').strip()
    delete_media = bool(data.get('delete_media', True))

    if not system_id or not filename:
        return jsonify({"error": "ข้อมูลไม่ครบถ้วน"}), 400

    success, msg = mgr.delete_game(system_id, filename, delete_media=delete_media)
    if success:
        return jsonify({"success": True, "message": msg})
    return jsonify({"error": msg}), 400

@app.route('/api/restart_es', methods=['POST'])
def api_restart_es():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400

    success, msg = mgr.restart_emulationstation()
    if success:
        return jsonify({"success": True, "message": msg})
    return jsonify({"error": msg}), 400

@app.route('/api/discover', methods=['GET'])
def api_discover():
    import socket
    from concurrent.futures import ThreadPoolExecutor

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        subnet_prefix = '.'.join(local_ip.split('.')[:3]) + '.'
    except Exception:
        subnet_prefix = '192.168.1.'
        local_ip = '192.168.1.1'

    def check_ssh_port(ip):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            res = sock.connect_ex((ip, 22))
            sock.close()
            if res == 0:
                return ip
        except Exception:
            pass
        return None

    ips = [f"{subnet_prefix}{i}" for i in range(1, 255) if f"{subnet_prefix}{i}" != local_ip]
    with ThreadPoolExecutor(max_workers=60) as ex:
        found_ips = [ip for ip in ex.map(check_ssh_port, ips) if ip]

    return jsonify({
        "success": True,
        "local_ip": local_ip,
        "subnet_prefix": subnet_prefix,
        "found_ips": found_ips
    })

@app.route('/api/download_rom', methods=['GET'])
def api_download_rom():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400
    system_id = request.args.get('system', '').strip()
    filename = request.args.get('filename', '').strip()
    if not system_id or not filename:
        return jsonify({"error": "ข้อมูลไม่ครบถ้วน"}), 400

    stream = mgr.download_file_stream(system_id, filename)
    if not stream:
        return jsonify({"error": "ไม่พบไฟล์"}), 404

    return send_file(
        stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/octet-stream'
    )

@app.route('/api/download_save', methods=['GET'])
def api_download_save():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400
    system_id = request.args.get('system', '').strip()
    filename = request.args.get('filename', '').strip()
    if not system_id or not filename:
        return jsonify({"error": "ข้อมูลไม่ครบถ้วน"}), 400

    stream = mgr.download_file_stream(system_id, filename)
    if not stream:
        return jsonify({"error": "ไม่พบไฟล์เซฟ"}), 404

    return send_file(
        stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/octet-stream'
    )

@app.route('/api/backup_all_saves', methods=['GET'])
def api_backup_all_saves():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400

    zip_bytes = mgr.backup_all_saves_zip()
    if not zip_bytes:
        return jsonify({"error": "ไม่พบไฟล์เซฟในการ์ดความจำ"}), 404

    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    return send_file(
        io.BytesIO(zip_bytes),
        as_attachment=True,
        download_name=f"ArkOS_Saves_Backup_{date_str}.zip",
        mimetype='application/zip'
    )

@app.route('/api/batch_scrape', methods=['POST'])
def api_batch_scrape():
    mgr = get_manager()
    if not mgr or not mgr.is_connected():
        return jsonify({"error": "ยังไม่ได้เชื่อมต่อกับเครื่อง ArkOS"}), 400

    data = request.json or {}
    system_id = data.get('system', '').strip()
    if not system_id:
        return jsonify({"error": "กรุณาระบุระบบเกม"}), 400

    games = mgr.list_games(system_id)
    missing = [g for g in games if not g.get('has_cover')]

    updated = 0
    for g in missing:
        try:
            results = search_box_arts(g['display_name'], system_id)
            if results:
                top_img = results[0]['image_url']
                img_data = download_image_bytes(top_img)
                mgr.upload_cover_file(system_id, g['filename'], img_data, img_extension='.png')
                updated += 1
        except Exception:
            continue

    return jsonify({
        "success": True,
        "system": system_id,
        "total_uncovered": len(missing),
        "updated": updated
    })

if __name__ == '__main__':
    print("=" * 60)
    print("  ArkOS WiFi ROM & Box Art Manager")
    print("  เปิดเบราว์เซอร์ไปที่: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)
