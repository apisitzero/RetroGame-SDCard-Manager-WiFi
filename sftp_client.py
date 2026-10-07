import os
import re
import posixpath
import threading
import xml.etree.ElementTree as ET
from xml.dom import minidom
import paramiko
from typing import Dict, List, Optional, Tuple

SYSTEM_METADATA = {
    "gba": {"name": "Game Boy Advance", "exts": [".gba", ".zip", ".7z"], "icon": "gamepad"},
    "gb": {"name": "Game Boy", "exts": [".gb", ".zip", ".7z"], "icon": "gamepad"},
    "gbc": {"name": "Game Boy Color", "exts": [".gbc", ".zip", ".7z"], "icon": "gamepad"},
    "sfc": {"name": "Super Famicom / SNES", "exts": [".sfc", ".smc", ".zip", ".7z"], "icon": "tv"},
    "snes": {"name": "Super Nintendo", "exts": [".sfc", ".smc", ".zip", ".7z"], "icon": "tv"},
    "nes": {"name": "NES / Famicom", "exts": [".nes", ".fds", ".zip", ".7z"], "icon": "tv"},
    "fc": {"name": "Famicom", "exts": [".nes", ".fds", ".zip", ".7z"], "icon": "tv"},
    "psx": {"name": "PlayStation 1", "exts": [".iso", ".chd", ".bin", ".cue", ".pbp", ".img", ".m3u"], "icon": "compact-disc"},
    "ps1": {"name": "PlayStation 1", "exts": [".iso", ".chd", ".bin", ".cue", ".pbp", ".img", ".m3u"], "icon": "compact-disc"},
    "psp": {"name": "PSP (PlayStation Portable)", "exts": [".iso", ".cso", ".pbp", ".chd"], "icon": "mobile-alt"},
    "nds": {"name": "Nintendo DS", "exts": [".nds", ".zip", ".7z"], "icon": "tablet-alt"},
    "n64": {"name": "Nintendo 64", "exts": [".z64", ".n64", ".v64", ".zip", ".7z"], "icon": "cube"},
    "megadrive": {"name": "Sega Mega Drive / Genesis", "exts": [".md", ".gen", ".smd", ".bin", ".zip", ".7z"], "icon": "tv"},
    "genesis": {"name": "Sega Genesis", "exts": [".md", ".gen", ".smd", ".bin", ".zip", ".7z"], "icon": "tv"},
    "mastersystem": {"name": "Sega Master System", "exts": [".sms", ".zip", ".7z"], "icon": "tv"},
    "gamegear": {"name": "Sega Game Gear", "exts": [".gg", ".zip", ".7z"], "icon": "mobile-alt"},
    "dreamcast": {"name": "Sega Dreamcast", "exts": [".cdi", ".gdi", ".chd", ".iso"], "icon": "compact-disc"},
    "saturn": {"name": "Sega Saturn", "exts": [".chd", ".iso", ".cue", ".bin", ".m3u"], "icon": "compact-disc"},
    "sega32x": {"name": "Sega 32X", "exts": [".32x", ".zip", ".7z"], "icon": "tv"},
    "segacd": {"name": "Sega CD", "exts": [".chd", ".iso", ".cue", ".bin", ".m3u"], "icon": "compact-disc"},
    "mame": {"name": "MAME / Arcade", "exts": [".zip", ".7z", ".chd"], "icon": "gamepad"},
    "arcade": {"name": "Arcade", "exts": [".zip", ".7z", ".chd"], "icon": "gamepad"},
    "fbneo": {"name": "FinalBurn Neo", "exts": [".zip", ".7z"], "icon": "gamepad"},
    "neogeo": {"name": "Neo Geo", "exts": [".zip", ".7z"], "icon": "gamepad"},
    "pce": {"name": "PC Engine / TurboGrafx-16", "exts": [".pce", ".cue", ".chd", ".zip", ".7z"], "icon": "tv"},
    "pcecd": {"name": "PC Engine CD", "exts": [".chd", ".cue", ".iso"], "icon": "compact-disc"},
    "wonderswan": {"name": "WonderSwan", "exts": [".ws", ".wsc", ".zip", ".7z"], "icon": "mobile-alt"},
    "cps1": {"name": "Capcom CPS-1", "exts": [".zip", ".7z"], "icon": "gamepad"},
    "cps2": {"name": "Capcom CPS-2", "exts": [".zip", ".7z"], "icon": "gamepad"},
    "cps3": {"name": "Capcom CPS-3", "exts": [".zip", ".7z"], "icon": "gamepad"},
    "atari2600": {"name": "Atari 2600", "exts": [".a26", ".bin", ".zip", ".7z"], "icon": "tv"},
    "atari7800": {"name": "Atari 7800", "exts": [".a78", ".bin", ".zip", ".7z"], "icon": "tv"},
    "lynx": {"name": "Atari Lynx", "exts": [".lnx", ".zip", ".7z"], "icon": "mobile-alt"},
    "openbor": {"name": "OpenBOR", "exts": [".pak"], "icon": "gamepad"},
    "ports": {"name": "PortMaster / Ports", "exts": [".sh"], "icon": "terminal"},
    "pico8": {"name": "PICO-8", "exts": [".p8", ".png"], "icon": "cubes"}
}

MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SKIP_NAMES = {"images", "boxart", "media", "downloaded_images", "gamelist.xml", "gamelist.xml.bak", "gamelist.xml.orig", "lost+found", "system"}

class ArkOSManager:
    def __init__(self, host: str, port: int = 22, username: str = "ark", password: str = "ark", roms_root: str = "auto"):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.roms_root = roms_root
        self.ssh: Optional[paramiko.SSHClient] = None
        self.sftp: Optional[paramiko.SFTPClient] = None
        self.detected_root: Optional[str] = None
        self.lock = threading.RLock()

    def connect(self) -> Tuple[bool, str]:
        with self.lock:
            try:
                self.close()
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=8,
                    banner_timeout=10,
                    allow_agent=False,
                    look_for_keys=False
                )
                self.ssh = ssh
                self.sftp = ssh.open_sftp()
                
                # Detect ROMs root path
                self.detected_root = self._detect_roms_root()
                if not self.detected_root:
                    return False, "เชื่อมต่อได้ แต่ไม่พบโฟลเดอร์ /roms หรือ /roms2 ของ ArkOS"
                    
                return True, f"เชื่อมต่อ ArkOS สำเร็จ! (พบตำแหน่งเมม: {self.detected_root})"
            except Exception as e:
                self.close()
                return False, f"เชื่อมต่อไม่สำเร็จ: {str(e)}"

    def close(self):
        with self.lock:
            if self.sftp:
                try:
                    self.sftp.close()
                except Exception:
                    pass
                self.sftp = None
            if self.ssh:
                try:
                    self.ssh.close()
                except Exception:
                    pass
                self.ssh = None

    def is_connected(self) -> bool:
        if not self.ssh or not self.sftp:
            return False
        try:
            transport = self.ssh.get_transport()
            return transport is not None and transport.is_active()
        except Exception:
            return False

    def _detect_roms_root(self) -> Optional[str]:
        if self.roms_root and self.roms_root != "auto":
            try:
                self.sftp.stat(self.roms_root)
                return self.roms_root
            except Exception:
                pass

        candidates = ["/roms2", "/roms", "/media/ROM", "/media/ROMS", "/roms/bios/../", "/storage/roms"]
        for path in candidates:
            try:
                st = self.sftp.stat(path)
                entries = self.sftp.listdir(path)
                known_hits = sum(1 for e in entries if e.lower() in SYSTEM_METADATA)
                if known_hits >= 2 or ("gba" in entries or "sfc" in entries or "nes" in entries or "psx" in entries):
                    return path
            except Exception:
                continue
                
        try:
            self.sftp.stat("/roms")
            return "/roms"
        except Exception:
            pass
        return None

    def get_disk_usage(self) -> Dict[str, any]:
        if not self.is_connected() or not self.detected_root:
            return {"error": "Not connected"}
        with self.lock:
            try:
                stdin, stdout, stderr = self.ssh.exec_command(f"df -k '{self.detected_root}'", timeout=5)
                lines = stdout.read().decode('utf-8', errors='ignore').strip().split('\n')
                if len(lines) >= 2:
                    parts = lines[1].split()
                    total_kb = int(parts[1])
                    used_kb = int(parts[2])
                    avail_kb = int(parts[3])
                    
                    total_gb = round(total_kb / (1024 * 1024), 2)
                    used_gb = round(used_kb / (1024 * 1024), 2)
                    free_gb = round(avail_kb / (1024 * 1024), 2)
                    percent = round((used_kb / max(total_kb, 1)) * 100, 1)
                    
                    return {
                        "total_gb": total_gb,
                        "used_gb": used_gb,
                        "free_gb": free_gb,
                        "percent": percent,
                        "path": self.detected_root
                    }
            except Exception as e:
                return {"error": str(e)}
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0, "path": self.detected_root}

    def list_systems(self) -> List[Dict[str, any]]:
        if not self.is_connected() or not self.detected_root:
            return []
        
        systems = []
        with self.lock:
            try:
                entries = self.sftp.listdir(self.detected_root)
                for entry in entries:
                    if entry.startswith('.') or entry.lower() in ["lost+found", "bios", "tools", "backup"]:
                        continue
                    full_path = posixpath.join(self.detected_root, entry)
                    try:
                        attr = self.sftp.stat(full_path)
                        import stat
                        if stat.S_ISDIR(attr.st_mode):
                            sys_key = entry.lower()
                            meta = SYSTEM_METADATA.get(sys_key, {
                                "name": entry.upper(),
                                "exts": [],
                                "icon": "folder"
                            })
                            
                            files = self.sftp.listdir(full_path)
                            game_count = 0
                            for f in files:
                                if f.startswith('.') or f.lower() in SKIP_NAMES:
                                    continue
                                ext = posixpath.splitext(f)[1].lower()
                                if ext not in MEDIA_EXTS and ext not in {".txt", ".xml", ".sav", ".srm", ".state"}:
                                    game_count += 1
                            
                            systems.append({
                                "id": entry,
                                "name": meta["name"],
                                "icon": meta["icon"],
                                "game_count": game_count,
                                "path": full_path
                            })
                    except Exception:
                        continue
            except Exception as e:
                print("Error listing systems:", e)
        
        systems.sort(key=lambda x: (x["game_count"] == 0, -x["game_count"], x["name"].lower()))
        return systems

    def _parse_gamelist(self, system_id: str) -> Dict[str, Dict[str, str]]:
        """Parses gamelist.xml for a system and returns metadata mapping"""
        metadata_map = {}
        if not self.detected_root:
            return metadata_map
            
        xml_path = posixpath.join(self.detected_root, system_id, "gamelist.xml")
        try:
            with self.lock:
                with self.sftp.open(xml_path, 'r') as f:
                    content = f.read().decode('utf-8', errors='ignore')
            
            root = ET.fromstring(content)
            for game_el in root.findall('game'):
                path_el = game_el.find('path')
                if path_el is not None and path_el.text:
                    raw_path = path_el.text.strip()
                    clean_rel = raw_path.lstrip('./').lstrip('/')
                    filename = posixpath.basename(clean_rel)
                    
                    name_el = game_el.find('name')
                    desc_el = game_el.find('desc')
                    image_el = game_el.find('image')
                    dev_el = game_el.find('developer')
                    pub_el = game_el.find('publisher')
                    genre_el = game_el.find('genre')
                    releasedate_el = game_el.find('releasedate')
                    
                    item = {
                        "path": raw_path,
                        "rel_path": clean_rel,
                        "filename": filename,
                        "name": name_el.text.strip() if (name_el is not None and name_el.text) else "",
                        "desc": desc_el.text.strip() if (desc_el is not None and desc_el.text) else "",
                        "image": image_el.text.strip() if (image_el is not None and image_el.text) else "",
                        "developer": dev_el.text.strip() if (dev_el is not None and dev_el.text) else "",
                        "publisher": pub_el.text.strip() if (pub_el is not None and pub_el.text) else "",
                        "genre": genre_el.text.strip() if (genre_el is not None and genre_el.text) else "",
                        "releasedate": releasedate_el.text.strip() if (releasedate_el is not None and releasedate_el.text) else ""
                    }
                    
                    # Store multiple keys for fast lookups
                    metadata_map[clean_rel.lower()] = item
                    metadata_map[filename.lower()] = item
                    if '/' in clean_rel:
                        top_dir = clean_rel.split('/')[0].lower()
                        metadata_map[top_dir] = item
        except Exception:
            pass
        return metadata_map

    def list_games(self, system_id: str) -> List[Dict[str, any]]:
        if not self.is_connected() or not self.detected_root:
            return []
            
        system_dir = posixpath.join(self.detected_root, system_id)
        gamelist_meta = self._parse_gamelist(system_id)
        
        existing_images = {}
        with self.lock:
            try:
                images_dir = posixpath.join(system_dir, "images")
                for img in self.sftp.listdir(images_dir):
                    existing_images[img.lower()] = img
            except Exception:
                pass

        games = []
        with self.lock:
            try:
                entries = self.sftp.listdir_attr(system_dir)
                import stat
                
                existing_saves = {}
                for attr in entries:
                    f_name = attr.filename
                    ext_l = posixpath.splitext(f_name)[1].lower()
                    if ext_l in {".sav", ".srm", ".state"}:
                        b_name = posixpath.splitext(f_name)[0].lower()
                        existing_saves[b_name] = f_name

                for attr in entries:
                    filename = attr.filename
                    if filename.startswith('.') or filename.lower() in SKIP_NAMES:
                        continue
                    
                    is_dir = stat.S_ISDIR(attr.st_mode)
                    
                    # For directories (e.g. PlayStation 1 folder games)
                    if is_dir:
                        base_name = filename
                        meta = gamelist_meta.get(filename.lower(), {})
                        display_name = meta.get("name") or base_name
                        
                        cover_rel_path = None
                        if meta.get("image"):
                            cover_rel_path = meta.get("image")
                        else:
                            candidates = [
                                f"{base_name}-image.png", f"{base_name}.png", f"{base_name}-image.jpg", f"{base_name}.jpg",
                                f"{base_name}-thumb.png"
                            ]
                            for cand in candidates:
                                if cand.lower() in existing_images:
                                    cover_rel_path = f"./images/{existing_images[cand.lower()]}"
                                    break

                        save_found = existing_saves.get(base_name.lower())
                        games.append({
                            "filename": filename,
                            "display_name": display_name,
                            "size_str": "โฟลเดอร์",
                            "size_bytes": 0,
                            "system": system_id,
                            "is_dir": True,
                            "has_cover": bool(cover_rel_path),
                            "cover_path": cover_rel_path or "",
                            "has_save": bool(save_found),
                            "save_filename": save_found or "",
                            "desc": meta.get("desc", ""),
                            "developer": meta.get("developer", ""),
                            "genre": meta.get("genre", "")
                        })
                        continue

                    ext = posixpath.splitext(filename)[1].lower()
                    if ext in {".sav", ".srm", ".state", ".state.auto", ".txt", ".xml", ".bak"}:
                        continue
                    if ext in MEDIA_EXTS:
                        continue

                    size_bytes = attr.st_size
                    if size_bytes >= 1024 * 1024 * 1024:
                        size_str = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
                    elif size_bytes >= 1024 * 1024:
                        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                    else:
                        size_str = f"{size_bytes / 1024:.0f} KB"

                    base_name = posixpath.splitext(filename)[0]
                    meta = gamelist_meta.get(filename.lower(), {})
                    display_name = meta.get("name") or base_name

                    cover_rel_path = None
                    if meta.get("image"):
                        cover_rel_path = meta.get("image")
                    else:
                        candidates = [
                            f"{base_name}-image.png",
                            f"{base_name}.png",
                            f"{base_name}-image.jpg",
                            f"{base_name}.jpg",
                            f"{base_name}-thumb.png"
                        ]
                        for cand in candidates:
                            if cand.lower() in existing_images:
                                cover_rel_path = f"./images/{existing_images[cand.lower()]}"
                                break

                    save_found = existing_saves.get(base_name.lower())

                    games.append({
                        "filename": filename,
                        "display_name": display_name,
                        "size_str": size_str,
                        "size_bytes": size_bytes,
                        "system": system_id,
                        "is_dir": False,
                        "has_cover": bool(cover_rel_path),
                        "cover_path": cover_rel_path or "",
                        "has_save": bool(save_found),
                        "save_filename": save_found or "",
                        "desc": meta.get("desc", ""),
                        "developer": meta.get("developer", ""),
                        "genre": meta.get("genre", "")
                    })
            except Exception as e:
                print(f"Error listing games for {system_id}:", e)
            
        games.sort(key=lambda x: x["display_name"].lower())
        return games

    def get_image_bytes(self, system_id: str, cover_path: str) -> Optional[bytes]:
        """Reads image binary data over SFTP safely using thread lock"""
        if not self.is_connected() or not self.detected_root:
            return None
        with self.lock:
            try:
                if cover_path.startswith('/'):
                    full_path = cover_path
                else:
                    clean_rel = cover_path.lstrip('./').lstrip('/')
                    full_path = posixpath.join(self.detected_root, system_id, clean_rel)
                
                with self.sftp.open(full_path, 'rb') as f:
                    return f.read()
            except Exception as e:
                return None

    def update_gamelist_entry(self, system_id: str, filename: str, new_name: Optional[str] = None, 
                              new_image_rel: Optional[str] = None, new_desc: Optional[str] = None,
                              new_dev: Optional[str] = None):
        if not self.detected_root:
            return False
            
        xml_path = posixpath.join(self.detected_root, system_id, "gamelist.xml")
        
        with self.lock:
            root = None
            try:
                with self.sftp.open(xml_path, 'r') as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    if content.strip():
                        root = ET.fromstring(content)
            except Exception:
                root = None

            if root is None or root.tag != 'gameList':
                root = ET.Element('gameList')

            target_game = None
            for game_el in root.findall('game'):
                path_el = game_el.find('path')
                if path_el is not None and path_el.text:
                    if posixpath.basename(path_el.text.strip()) == filename:
                        target_game = game_el
                        break

            if target_game is None:
                target_game = ET.SubElement(root, 'game')
                path_el = ET.SubElement(target_game, 'path')
                path_el.text = f"./{filename}"

            if new_name is not None:
                name_el = target_game.find('name')
                if name_el is None:
                    name_el = ET.SubElement(target_game, 'name')
                name_el.text = new_name

            if new_image_rel is not None:
                img_el = target_game.find('image')
                if img_el is None:
                    img_el = ET.SubElement(target_game, 'image')
                img_el.text = new_image_rel

            if new_desc is not None:
                desc_el = target_game.find('desc')
                if desc_el is None:
                    desc_el = ET.SubElement(target_game, 'desc')
                desc_el.text = new_desc

            if new_dev is not None:
                dev_el = target_game.find('developer')
                if dev_el is None:
                    dev_el = ET.SubElement(target_game, 'developer')
                dev_el.text = new_dev

            xml_str = ET.tostring(root, encoding='utf-8')
            try:
                parsed_str = minidom.parseString(xml_str)
                pretty_xml = parsed_str.toprettyxml(indent="  ", encoding="utf-8")
            except Exception:
                pretty_xml = xml_str

            with self.sftp.open(xml_path, 'wb') as f:
                f.write(pretty_xml)
        return True

    def remove_gamelist_entry(self, system_id: str, filename: str):
        if not self.detected_root:
            return
        xml_path = posixpath.join(self.detected_root, system_id, "gamelist.xml")
        with self.lock:
            try:
                with self.sftp.open(xml_path, 'r') as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    root = ET.fromstring(content)
                    changed = False
                    for game_el in root.findall('game'):
                        path_el = game_el.find('path')
                        if path_el is not None and path_el.text and posixpath.basename(path_el.text.strip()) == filename:
                            root.remove(game_el)
                            changed = True
                    if changed:
                        xml_str = ET.tostring(root, encoding='utf-8')
                        with self.sftp.open(xml_path, 'wb') as out_f:
                            out_f.write(xml_str)
            except Exception:
                pass

    def upload_rom_file(self, system_id: str, filename: str, file_stream, display_name: Optional[str] = None) -> bool:
        if not self.is_connected() or not self.detected_root:
            return False
            
        dest_path = posixpath.join(self.detected_root, system_id, filename)
        with self.lock:
            with self.sftp.open(dest_path, 'wb') as remote_f:
                while True:
                    chunk = file_stream.read(65536)
                    if not chunk:
                        break
                    remote_f.write(chunk)
                    
        base_name = posixpath.splitext(filename)[0]
        final_name = display_name if display_name else base_name
        self.update_gamelist_entry(system_id, filename, new_name=final_name)
        return True

    def upload_cover_file(self, system_id: str, rom_filename: str, image_bytes: bytes, img_extension: str = ".png") -> str:
        if not self.is_connected() or not self.detected_root:
            raise Exception("Not connected")
            
        system_dir = posixpath.join(self.detected_root, system_id)
        images_dir = posixpath.join(system_dir, "images")
        
        with self.lock:
            try:
                self.sftp.stat(images_dir)
            except Exception:
                try:
                    self.sftp.mkdir(images_dir)
                except Exception:
                    pass
                    
            base_name = posixpath.splitext(rom_filename)[0]
            cover_filename = f"{base_name}-image{img_extension}"
            remote_cover_path = posixpath.join(images_dir, cover_filename)
            
            with self.sftp.open(remote_cover_path, 'wb') as remote_f:
                remote_f.write(image_bytes)
                
        rel_path = f"./images/{cover_filename}"
        self.update_gamelist_entry(system_id, rom_filename, new_image_rel=rel_path)
        return rel_path

    def rename_game(self, system_id: str, old_filename: str, new_display_name: str, rename_rom_file: bool = False, new_filename: Optional[str] = None) -> Tuple[bool, str]:
        if not self.is_connected() or not self.detected_root:
            return False, "Not connected"
            
        system_dir = posixpath.join(self.detected_root, system_id)
        current_filename = old_filename
        
        with self.lock:
            if rename_rom_file and new_filename and new_filename != old_filename:
                old_full = posixpath.join(system_dir, old_filename)
                new_full = posixpath.join(system_dir, new_filename)
                try:
                    self.sftp.rename(old_full, new_full)
                    current_filename = new_filename
                    
                    old_base = posixpath.splitext(old_filename)[0]
                    new_base = posixpath.splitext(new_filename)[0]
                    for save_ext in [".sav", ".srm", ".state"]:
                        try:
                            self.sftp.rename(
                                posixpath.join(system_dir, f"{old_base}{save_ext}"),
                                posixpath.join(system_dir, f"{new_base}{save_ext}")
                            )
                        except Exception:
                            pass
                            
                    self.remove_gamelist_entry(system_id, old_filename)
                except Exception as e:
                    return False, f"เปลี่ยนชื่อไฟล์ไม่สำเร็จ: {str(e)}"
                    
        self.update_gamelist_entry(system_id, current_filename, new_name=new_display_name)
        return True, "เปลี่ยนชื่อสำเร็จ"

    def delete_game(self, system_id: str, filename: str, delete_media: bool = True) -> Tuple[bool, str]:
        if not self.is_connected() or not self.detected_root:
            return False, "Not connected"
            
        system_dir = posixpath.join(self.detected_root, system_id)
        rom_path = posixpath.join(system_dir, filename)
        
        with self.lock:
            try:
                # Check if file or directory
                attr = self.sftp.stat(rom_path)
                import stat
                if stat.S_ISDIR(attr.st_mode):
                    self._rmdir_recursive(rom_path)
                else:
                    self.sftp.remove(rom_path)
            except Exception as e:
                return False, f"ลบไฟล์เกมไม่สำเร็จ: {str(e)}"
                
            base_name = posixpath.splitext(filename)[0]
            
            for save_ext in [".sav", ".srm", ".state", ".state.auto"]:
                try:
                    self.sftp.remove(posixpath.join(system_dir, f"{base_name}{save_ext}"))
                except Exception:
                    pass
                    
            if delete_media:
                for img_cand in [f"{base_name}-image.png", f"{base_name}.png", f"{base_name}-image.jpg", f"{base_name}.jpg"]:
                    try:
                        self.sftp.remove(posixpath.join(system_dir, "images", img_cand))
                    except Exception:
                        pass
                        
            self.remove_gamelist_entry(system_id, filename)
        return True, "ลบเกมเรียบร้อยแล้ว"

    def _rmdir_recursive(self, path: str):
        for f in self.sftp.listdir_attr(path):
            import stat
            sub_path = posixpath.join(path, f.filename)
            if stat.S_ISDIR(f.st_mode):
                self._rmdir_recursive(sub_path)
            else:
                self.sftp.remove(sub_path)
        self.sftp.rmdir(path)

    def download_file_stream(self, system_id: str, filename: str):
        if not self.is_connected() or not self.detected_root:
            return None
        file_path = posixpath.join(self.detected_root, system_id, filename)
        with self.lock:
            return self.sftp.open(file_path, 'rb')

    def backup_all_saves_zip(self) -> Optional[bytes]:
        if not self.is_connected() or not self.detected_root:
            return None
            
        import io
        import zipfile
        zip_buf = io.BytesIO()
        
        with self.lock:
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for sys_dir in self.sftp.listdir(self.detected_root):
                    full_sys = posixpath.join(self.detected_root, sys_dir)
                    try:
                        entries = self.sftp.listdir(full_sys)
                        for f in entries:
                            ext = posixpath.splitext(f)[1].lower()
                            if ext in {".sav", ".srm", ".state", ".state.auto"}:
                                save_path = posixpath.join(full_sys, f)
                                with self.sftp.open(save_path, 'rb') as sf:
                                    data = sf.read()
                                    zf.writestr(f"{sys_dir}/{f}", data)
                    except Exception:
                        continue
                        
        zip_buf.seek(0)
        return zip_buf.getvalue()

    def restart_emulationstation(self) -> Tuple[bool, str]:
        if not self.is_connected():
            return False, "Not connected"
        with self.lock:
            try:
                cmd = "sudo killall emulationstation 2>/dev/null; sleep 1; sudo systemctl restart emulationstation 2>/dev/null || (sleep 1 && emulationstation &)"
                stdin, stdout, stderr = self.ssh.exec_command(cmd, timeout=5)
                return True, "สั่งรีสตาร์ท EmulationStation บนเครื่อง ArkOS แล้ว! หน้ารวมเกมจะรีเฟรชในไม่กี่วินาที"
            except Exception as e:
                return False, f"ไม่สามารถรีสตาร์ท ES ได้: {str(e)}"
