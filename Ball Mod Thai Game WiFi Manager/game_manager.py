# -*- coding: utf-8 -*-
"""
ArkOS On-Device Game Manager & Token Dictionary (v1.1)
Part of: RetroGame & SD Card Manager Version WiFi
Created for: เพจเล่าเรื่องเกม (Lao Reuang Game) & BallModThaiGame
Author: AntiGravity
"""

import os
import io
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import time
import mimetypes
import hashlib
import re

SYSTEM_NAMES = {
    "gba": "Game Boy Advance",
    "gb": "Game Boy",
    "gbc": "Game Boy Color",
    "psx": "PlayStation 1",
    "sfc": "Super Famicom / SNES",
    "snes": "Super Nintendo",
    "nes": "Famicom / NES",
    "fc": "Famicom",
    "megadrive": "Sega Mega Drive / Genesis",
    "genesis": "Sega Genesis",
    "nds": "Nintendo DS",
    "psp": "PlayStation Portable",
    "n64": "Nintendo 64",
    "arcade": "Arcade Games",
    "mame": "MAME Arcade",
    "neogeo": "Neo Geo",
    "fbneo": "FinalBurn Neo",
    "pce": "PC Engine / TurboGrafx-16",
    "pcengine": "PC Engine",
    "wonderswan": "WonderSwan",
    "wsc": "WonderSwan Color",
    "gamegear": "Sega Game Gear",
    "mastersystem": "Sega Master System",
    "segacd": "Sega CD",
    "sega32x": "Sega 32X",
    "atarilynx": "Atari Lynx",
    "atari2600": "Atari 2600",
    "atari7800": "Atari 7800",
    "ports": "Ports Collection",
    "pico8": "PICO-8",
    "dreamcast": "Sega Dreamcast",
    "saturn": "Sega Saturn"
}

SYSTEM_ICONS = {
    "gba": "gamepad",
    "gb": "gamepad",
    "gbc": "gamepad",
    "psx": "compact-disc",
    "sfc": "gamepad",
    "snes": "gamepad",
    "nes": "gamepad",
    "fc": "gamepad",
    "megadrive": "gamepad",
    "nds": "mobile-screen",
    "psp": "gamepad",
    "n64": "cubes",
    "arcade": "vr-cardboard",
    "mame": "vr-cardboard",
    "neogeo": "vr-cardboard",
    "pce": "gamepad",
    "ports": "folder-open",
    "dreamcast": "compact-disc"
}

SAVE_EXTENSIONS = {'.srm', '.sav', '.state', '.state0', '.state1', '.state2', '.state3', '.state4', '.state5'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
ROM_EXTENSIONS = {
    '.zip', '.7z', '.gba', '.gb', '.gbc', '.nes', '.sfc', '.smc', '.bin',
    '.cue', '.iso', '.chd', '.pbp', '.nds', '.n64', '.z64', '.v64',
    '.md', '.gen', '.pce', '.ws', '.wsc', '.gg', '.sms', '.cdi', '.gdi',
    '.img', '.mdf', '.ccd', '.sub', '.m3u'
}
FOLDER_GAME_EXTENSIONS = (
    '.m3u', '.cue', '.chd', '.pbp', '.iso', '.ccd', '.img', '.bin', '.mdf', '.zip', '.7z'
)

class ArkOSGameManager:
    def __init__(self, roms_root=None):
        self.roms_root = self._detect_roms_root(roms_root)
        self.token_registry = {}  # token -> full internal game dict
        self.cache = {}           # system_id -> {'xml_mtime': ..., 'games': [...]}
        self.cheats_dir = os.path.join(self.roms_root, "cheats")
        os.makedirs(self.cheats_dir, exist_ok=True)
        print(f"[ArkOSGameManager v1.1] Using ROMs root: {self.roms_root}")

    def _detect_roms_root(self, preferred_path=None):
        """Auto-detect ArkOS ROMs directory across SD1 and SD2."""
        if preferred_path and os.path.exists(preferred_path):
            return os.path.abspath(preferred_path)

        candidates = []

        candidates.extend([
            "/roms2",                     # ArkOS SD Slot 2 (Dual SD setup)
            "/roms",                      # ArkOS SD Slot 1 (Single SD setup)
            "/mnt/roms",
            "/media/roms",
            "./roms",                     # Local development folder
            "../roms"
        ])

        for p in candidates:
            if os.path.exists(p) and os.path.isdir(p):
                try:
                    subdirs = [d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d))]
                    if any(s in subdirs for s in ['gba', 'psx', 'nes', 'sfc', 'megadrive', 'ports']):
                        return os.path.abspath(p)
                except Exception:
                    pass

        fallback = os.path.abspath("./roms")
        os.makedirs(fallback, exist_ok=True)
        return fallback

    def get_disk_info(self):
        """Get disk usage of the ROMs partition."""
        try:
            total, used, free = shutil.disk_usage(self.roms_root)
            total_gb = round(total / (1024 ** 3), 2)
            used_gb = round(used / (1024 ** 3), 2)
            free_gb = round(free / (1024 ** 3), 2)
            percent = round((used / total) * 100, 1) if total > 0 else 0
            return {
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "percent": percent,
                "root_path": self.roms_root
            }
        except Exception as e:
            return {
                "total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0,
                "root_path": self.roms_root, "error": str(e)
            }

    def _find_folder_game_file(self, folder_path):
        """
        Recursively scans a game directory (up to 3 levels deep) to find the primary launchable ROM.
        Returns a tuple: (rel_file_path, primary_filename, total_folder_size) or (None, None, 0)
        Priority: .m3u > .cue > .chd > .pbp > .iso > .ccd > .img > .bin > other
        """
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return None, None, 0

        found_files = []
        total_size = 0

        try:
            for root, dirs, files in os.walk(folder_path):
                # Avoid hidden folders and media folders inside game directory
                dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in ('media', 'images', 'boxart', 'downloaded_images', '.tmp_uploads')]
                
                rel_root = os.path.relpath(root, folder_path)
                depth = 0 if rel_root == '.' else len(Path(rel_root).parts)
                if depth > 3:
                    continue

                for f in files:
                    if f.startswith('.'):
                        continue
                    full_p = os.path.join(root, f)
                    try:
                        fsize = os.path.getsize(full_p)
                        total_size += fsize
                    except Exception:
                        fsize = 0

                    ext = os.path.splitext(f)[1].lower()
                    if ext in FOLDER_GAME_EXTENSIONS:
                        rel_p = os.path.relpath(full_p, folder_path).replace('\\', '/')
                        found_files.append((f, rel_p, ext, fsize))
        except Exception:
            pass

        if not found_files:
            return None, None, total_size

        ext_priority = {
            '.m3u': 1,
            '.cue': 2,
            '.chd': 3,
            '.pbp': 4,
            '.iso': 5,
            '.ccd': 6,
            '.img': 7,
            '.mdf': 8,
            '.bin': 9,
            '.zip': 10,
            '.7z': 11
        }

        def file_sort_key(item):
            fname, rel_p, ext, fsize = item
            fname_lower = fname.lower()
            prio = ext_priority.get(ext, 99)
            
            # For .bin files: penalize secondary audio tracks like "track 2", "track 3"
            track_penalty = 0
            if ext == '.bin':
                if re.search(r'track\s*0*[2-9]', fname_lower) or re.search(r'track\s*[1-9][0-9]', fname_lower):
                    track_penalty = 100
                elif 'track 1' in fname_lower or 'track 01' in fname_lower or 'track01' in fname_lower:
                    track_penalty = -5

            depth = len(Path(rel_p).parts)
            return (prio, track_penalty, depth, -fsize)

        found_files.sort(key=file_sort_key)
        best = found_files[0]
        return best[1], best[0], total_size

    def _count_system_games(self, sys_path, system_id=None):
        """Ultra-fast count of valid game ROMs in a system directory."""
        if not os.path.exists(sys_path) or not os.path.isdir(sys_path):
            return 0
        try:
            count = 0
            with os.scandir(sys_path) as it:
                for entry in it:
                    name_lower = entry.name.lower()
                    if name_lower.startswith('.') or name_lower in ('gamelist.xml', 'images', 'boxart', 'downloaded_images', 'media', 'cheats', '.tmp_uploads'):
                        continue
                    if entry.is_file():
                        ext = os.path.splitext(name_lower)[1]
                        if ext in ROM_EXTENSIONS:
                            count += 1
                    elif entry.is_dir():
                        # Subfolder game check (e.g. PS1 / Saturn folder)
                        rel_f, _, _ = self._find_folder_game_file(entry.path)
                        if rel_f:
                            count += 1
            return count
        except Exception:
            return 0

    def list_systems(self, is_premium=True, include_empty=False):
        """
        List available systems.
        - Requirement 1: Filters out empty folders (game_count == 0).
        - Requirement 2: Includes game_count for each system.
        - Requirement 3: Sorts systems by game_count descending (most games first).
        """
        systems = []
        if not os.path.exists(self.roms_root):
            return systems

        try:
            entries = sorted(os.listdir(self.roms_root))
        except Exception:
            return systems

        for name in entries:
            full_path = os.path.join(self.roms_root, name)
            if not os.path.isdir(full_path) or name.startswith('.'):
                continue

            # Free tier: Filter out non-game folders (e.g. bios, cheats, backup)
            if not is_premium:
                if name.lower() in ('cheats', 'bios', 'backup', 'tools', 'system'):
                    continue

            game_count = self._count_system_games(full_path, name)

            # 1. Hide folders that have 0 games unless include_empty is True
            if not include_empty and game_count == 0:
                continue

            display_name = SYSTEM_NAMES.get(name.lower(), name.upper())
            icon = SYSTEM_ICONS.get(name.lower(), "gamepad")

            systems.append({
                "id": name,
                "name": display_name,
                "path": full_path,
                "icon": icon,
                "game_count": game_count
            })

        # 3. Sort folders: most games first, then alphabetically
        systems.sort(key=lambda s: (-s["game_count"], s["name"].lower()))

        return systems

    def list_games(self, system_id, force_refresh=False, is_premium=True):
        """
        List games with Token Dictionary mapping and RAM caching.
        Filters save files and cheats if Free tier.
        """
        sys_path = os.path.join(self.roms_root, system_id)
        if not os.path.exists(sys_path) or not os.path.isdir(sys_path):
            return []

        gamelist_path = os.path.join(sys_path, "gamelist.xml")
        xml_mtime = os.path.getmtime(gamelist_path) if os.path.exists(gamelist_path) else 0

        # In-memory cache check
        cache_key = f"{system_id}_{is_premium}"
        if not force_refresh and cache_key in self.cache:
            cached_entry = self.cache[cache_key]
            if cached_entry['xml_mtime'] == xml_mtime:
                return cached_entry['games']

        # Parse XML
        xml_games = {}
        if os.path.exists(gamelist_path):
            xml_games = self._parse_gamelist(gamelist_path, sys_path)

        games_list = []
        try:
            all_entries = sorted(os.listdir(sys_path), key=lambda s: s.lower())
        except Exception:
            all_entries = []

        seen_roms = set()

        for entry in all_entries:
            if entry.startswith('.') or entry.lower() in ('gamelist.xml', 'images', 'boxart', 'downloaded_images', 'media', 'cheats', '.tmp_uploads'):
                continue

            entry_path = os.path.join(sys_path, entry)
            is_dir = os.path.isdir(entry_path)
            ext = os.path.splitext(entry)[1].lower()

            # Handle folder-based games (like in PS1 or Saturn)
            if is_dir:
                rel_game_file, primary_fname, folder_size = self._find_folder_game_file(entry_path)
                if not rel_game_file:
                    continue
                rom_filename = entry
                main_file = os.path.normpath(os.path.join(entry, rel_game_file)).replace('\\', '/')
                size_bytes = folder_size
            else:
                if ext not in ROM_EXTENSIONS:
                    continue
                rom_filename = entry
                main_file = entry
                try:
                    size_bytes = os.path.getsize(entry_path)
                except Exception:
                    size_bytes = 0

            seen_roms.add(rom_filename.lower())

            # Deterministic unique token: permanent hash based on system and rom filename
            clean_token_key = f"{system_id}_{rom_filename}".lower()
            token_hash = hashlib.md5(clean_token_key.encode('utf-8')).hexdigest()[:12]
            token = f"t_{system_id}_{token_hash}"

            size_str = self._format_size(size_bytes)

            base_name = os.path.splitext(rom_filename)[0]
            clean_base = self._clean_title(base_name).lower()

            # Metadata matching from gamelist.xml
            meta = (
                xml_games.get(rom_filename.lower()) or
                xml_games.get(main_file.lower()) or
                xml_games.get(clean_base) or
                xml_games.get(os.path.basename(main_file).lower()) or
                {}
            )
            display_name = meta.get('name') or base_name
            desc = meta.get('desc', '')

            # Check cover
            cover_path = meta.get('image')
            has_cover = False
            full_cover_path = None
            if cover_path:
                full_cover_path = self._resolve_cover_path(cover_path, sys_path)
                has_cover = bool(full_cover_path and os.path.exists(full_cover_path))

            # If not in XML or file missing, check inside game folder if folder-based game
            if not has_cover and is_dir:
                for img_candidate in ['cover.png', 'cover.jpg', 'folder.jpg', 'front.jpg', f"{entry}.png", f"{entry}.jpg", f"{base_name}.png", f"{base_name}.jpg"]:
                    cand_in_folder = os.path.join(entry_path, img_candidate)
                    if os.path.exists(cand_in_folder):
                        has_cover = True
                        full_cover_path = cand_in_folder
                        cover_path = f"./{entry}/{img_candidate}"
                        break

            # If still not found, search common cover folders
            if not has_cover:
                for img_dir in ['images', 'boxart', 'downloaded_images', 'media/boxart', 'media/images']:
                    for img_ext in ['.png', '.jpg', '.jpeg', '.webp']:
                        for suffix in ['-image', '', '_cover', '-boxart']:
                            # Try exact filename base
                            test_c = os.path.join(sys_path, img_dir, f"{base_name}{suffix}{img_ext}")
                            if os.path.exists(test_c):
                                has_cover = True
                                full_cover_path = test_c
                                cover_path = f"./{img_dir}/{os.path.basename(test_c)}"
                                break
                            # Try cleaned name base (without dump tags)
                            if clean_base:
                                test_c2 = os.path.join(sys_path, img_dir, f"{clean_base}{suffix}{img_ext}")
                                if os.path.exists(test_c2):
                                    has_cover = True
                                    full_cover_path = test_c2
                                    cover_path = f"./{img_dir}/{os.path.basename(test_c2)}"
                                    break
                        if has_cover:
                            break
                    if has_cover:
                        break

            cover_mtime = int(os.path.getmtime(full_cover_path)) if (has_cover and full_cover_path and os.path.exists(full_cover_path)) else 0

            # Check save file (Premium only)
            has_save = False
            save_filename = None
            save_abs_path = None

            for s_ext in SAVE_EXTENSIONS:
                s_path = os.path.join(sys_path, f"{base_name}{s_ext}")
                if os.path.exists(s_path):
                    has_save = True
                    save_filename = f"{base_name}{s_ext}"
                    save_abs_path = s_path
                    break

            # Check cheats file (.cht)
            has_cheats = False
            cht_path = self._find_cheat_file(system_id, rom_filename)
            if cht_path and os.path.exists(cht_path):
                has_cheats = True

            # Register internal token data
            internal_obj = {
                "token": token,
                "system": system_id,
                "filename": rom_filename,
                "is_dir": is_dir,
                "main_file": main_file,
                "rom_abs_path": entry_path,
                "display_name": display_name,
                "desc": desc,
                "size_bytes": size_bytes,
                "size_str": size_str,
                "has_cover": has_cover,
                "cover_rel_path": cover_path,
                "cover_abs_path": full_cover_path,
                "cover_mtime": cover_mtime,
                "has_save": has_save,
                "save_filename": save_filename,
                "save_abs_path": save_abs_path,
                "has_cheats": has_cheats,
                "cheat_abs_path": cht_path
            }
            self.token_registry[token] = internal_obj

            # Client-facing payload (Free vs Premium filtering)
            client_item = {
                "token": token,
                "system": system_id,
                "filename": rom_filename,
                "display_name": display_name,
                "size_str": size_str,
                "has_cover": has_cover,
                "cover_mtime": cover_mtime,
                "has_save": has_save if is_premium else False,
                "save_filename": save_filename if is_premium else None,
                "has_cheats": has_cheats if is_premium else False,
                "is_dir": is_dir
            }
            games_list.append(client_item)

        # Store in cache
        self.cache[cache_key] = {
            "xml_mtime": xml_mtime,
            "games": games_list
        }
        return games_list

    def _find_cheat_file(self, system_id, rom_filename):
        """Finds RetroArch .cht file for a given game."""
        base_name = os.path.splitext(rom_filename)[0]
        # Candidate 1: /roms/cheats/<system>/<base_name>.cht
        cand1 = os.path.join(self.cheats_dir, system_id, f"{base_name}.cht")
        if os.path.exists(cand1):
            return cand1

        # Candidate 2: /roms/<system>/<base_name>.cht
        cand2 = os.path.join(self.roms_root, system_id, f"{base_name}.cht")
        if os.path.exists(cand2):
            return cand2

        # Candidate 3: /roms/cheats/<base_name>.cht
        cand3 = os.path.join(self.cheats_dir, f"{base_name}.cht")
        if os.path.exists(cand3):
            return cand3

        return cand1  # Default target if created

    @staticmethod
    def _clean_title(text):
        """Strips dump tags like (USA), [!], (v1.1) for fuzzy matching."""
        if not text:
            return ""
        t = re.sub(r'\(.*?\)', '', text)
        t = re.sub(r'\[.*?\]', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    def _resolve_cover_path(self, cover_path_str, sys_path):
        """Resolves full absolute cover path across various ArkOS/EmulationStation path formats."""
        if not cover_path_str:
            return None
        p_str = cover_path_str.strip()

        # 1. Direct absolute path check
        if os.path.isabs(p_str) and os.path.exists(p_str):
            return p_str

        # 2. Check if absolute path starts with /roms/ or /roms2/ and re-map to current self.roms_root
        for prefix in ['/roms2/', '/roms/', '/mnt/roms/', '/media/roms/']:
            if p_str.startswith(prefix):
                rel_part = p_str[len(prefix):]  # e.g. 'gba/images/game-image.png'
                cand = os.path.join(self.roms_root, rel_part)
                if os.path.exists(cand):
                    return cand

        # 3. Check ~/.emulationstation
        if p_str.startswith('~'):
            expanded = os.path.expanduser(p_str)
            if os.path.exists(expanded):
                return expanded

        # 4. Standard relative path within sys_path (strip leading ./ or /)
        norm = p_str.lstrip('.').lstrip('/')
        cand = os.path.join(sys_path, norm)
        if os.path.exists(cand):
            return cand

        # 5. Check if filename exists inside sys_path/images or boxart or downloaded_images
        img_name = os.path.basename(p_str)
        for folder in ['images', 'boxart', 'downloaded_images', 'media/boxart', 'media/images']:
            cand = os.path.join(sys_path, folder, img_name)
            if os.path.exists(cand):
                return cand

        return None

    def _parse_gamelist(self, gamelist_path, sys_path):
        """Parse gamelist.xml efficiently with exact and clean title indexing."""
        result = {}
        try:
            tree = ET.parse(gamelist_path)
            root = tree.getroot()
            for game_elem in root.findall('game'):
                path_elem = game_elem.find('path')
                if path_elem is None or not path_elem.text:
                    continue
                rel_path = path_elem.text.strip().lstrip('.').lstrip('/')
                rel_path_clean = rel_path.replace('\\', '/')
                name_elem = game_elem.find('name')
                desc_elem = game_elem.find('desc')
                img_elem = game_elem.find('image')

                name = name_elem.text.strip() if (name_elem is not None and name_elem.text) else None
                desc = desc_elem.text.strip() if (desc_elem is not None and desc_elem.text) else ""
                image = img_elem.text.strip() if (img_elem is not None and img_elem.text) else None

                bname = os.path.basename(rel_path_clean).lower()
                clean_bname = self._clean_title(os.path.splitext(bname)[0]).lower()

                item = {
                    "name": name,
                    "desc": desc,
                    "image": image,
                    "path": rel_path_clean
                }
                result[bname] = item
                result[rel_path_clean.lower()] = item
                if clean_bname:
                    result[clean_bname] = item

                parts = Path(rel_path_clean).parts
                if len(parts) > 1:
                    folder_root = parts[0].lower()
                    result[folder_root] = item
                    clean_folder_root = self._clean_title(parts[0]).lower()
                    if clean_folder_root:
                        result[clean_folder_root] = item
        except Exception as e:
            print(f"[ArkOSGameManager] XML parse error {gamelist_path}: {e}")
        return result

    def _save_gamelist_tree(self, tree, system_id, sys_path):
        """Saves gamelist.xml to ROMs directory and mirrors to ~/.emulationstation if present."""
        gamelist_path = os.path.join(sys_path, "gamelist.xml")
        try:
            tree.write(gamelist_path, encoding='utf-8', xml_declaration=True)
        except Exception as e:
            print(f"[ArkOSGameManager] XML write error {gamelist_path}: {e}")

        # Mirror to ~/.emulationstation/gamelists/<system_id>/gamelist.xml if it exists
        es_user_path = os.path.expanduser(f"~/.emulationstation/gamelists/{system_id}/gamelist.xml")
        if os.path.exists(es_user_path):
            try:
                tree.write(es_user_path, encoding='utf-8', xml_declaration=True)
            except Exception as e:
                print(f"[ArkOSGameManager] Mirror XML write error {es_user_path}: {e}")

    def get_game_by_token(self, token):
        """Retrieve full game metadata via token."""
        return self.token_registry.get(token)

    def rename_game(self, token, new_display_name):
        """Update display name in gamelist.xml."""
        game = self.get_game_by_token(token)
        if not game:
            return {"success": False, "error": "Game token not found"}

        system_id = game["system"]
        sys_path = os.path.join(self.roms_root, system_id)
        gamelist_path = os.path.join(sys_path, "gamelist.xml")

        try:
            if os.path.exists(gamelist_path):
                tree = ET.parse(gamelist_path)
                root = tree.getroot()
            else:
                root = ET.Element("gameList")
                tree = ET.ElementTree(root)

            target_path_1 = f"./{game['filename']}".lower()
            target_path_2 = f"./{game['main_file']}".lower()
            found_elem = None

            for g_elem in root.findall('game'):
                p = g_elem.find('path')
                if p is not None and p.text:
                    clean_p = p.text.strip().lower()
                    if clean_p in (target_path_1, target_path_2, game['filename'].lower()):
                        found_elem = g_elem
                        break

            if found_elem is None:
                found_elem = ET.SubElement(root, 'game')
                p_elem = ET.SubElement(found_elem, 'path')
                p_elem.text = f"./{game['filename']}"

            n_elem = found_elem.find('name')
            if n_elem is None:
                n_elem = ET.SubElement(found_elem, 'name')
            n_elem.text = new_display_name

            self._save_gamelist_tree(tree, system_id, sys_path)

            self._clear_cache_for_system(system_id)
            game["display_name"] = new_display_name
            return {"success": True, "display_name": new_display_name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def apply_cover(self, token, image_bytes, filename_ext=".png"):
        """Save cover image directly to system/images and update gamelist.xml."""
        game = self.get_game_by_token(token)
        if not game:
            return {"success": False, "error": "Game token not found"}

        system_id = game["system"]
        sys_path = os.path.join(self.roms_root, system_id)
        images_dir = os.path.join(sys_path, "images")
        os.makedirs(images_dir, exist_ok=True)

        base_name = os.path.splitext(game["filename"])[0]
        cover_filename = f"{base_name}-image{filename_ext}"
        cover_abs_path = os.path.join(images_dir, cover_filename)
        rel_cover_path = f"./images/{cover_filename}"

        try:
            with open(cover_abs_path, 'wb') as f:
                f.write(image_bytes)

            # Update XML
            gamelist_path = os.path.join(sys_path, "gamelist.xml")
            if os.path.exists(gamelist_path):
                tree = ET.parse(gamelist_path)
                root = tree.getroot()
            else:
                root = ET.Element("gameList")
                tree = ET.ElementTree(root)

            target_path_1 = f"./{game['filename']}".lower()
            target_path_2 = f"./{game.get('main_file', '')}".lower()
            found_elem = None
            for g_elem in root.findall('game'):
                p = g_elem.find('path')
                if p is not None and p.text:
                    clean_p = p.text.strip().lower()
                    if clean_p in (target_path_1, target_path_2, game['filename'].lower()):
                        found_elem = g_elem
                        break

            if found_elem is None:
                found_elem = ET.SubElement(root, 'game')
                p_elem = ET.SubElement(found_elem, 'path')
                p_elem.text = f"./{game['filename']}"
                n_elem = ET.SubElement(found_elem, 'name')
                n_elem.text = game["display_name"]

            img_elem = found_elem.find('image')
            if img_elem is None:
                img_elem = ET.SubElement(found_elem, 'image')
            img_elem.text = rel_cover_path

            self._save_gamelist_tree(tree, system_id, sys_path)

            cover_mtime = int(os.path.getmtime(cover_abs_path)) if os.path.exists(cover_abs_path) else int(time.time())
            self._clear_cache_for_system(system_id)
            game["has_cover"] = True
            game["cover_abs_path"] = cover_abs_path
            game["cover_rel_path"] = rel_cover_path
            game["cover_mtime"] = cover_mtime

            return {"success": True, "cover_path": rel_cover_path, "cover_mtime": cover_mtime, "token": token}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_game(self, token):
        """Delete game ROM, cover image, and save file safely via token."""
        game = self.get_game_by_token(token)
        if not game:
            return {"success": False, "error": "Game token not found"}

        system_id = game["system"]
        try:
            if os.path.exists(game["rom_abs_path"]):
                if game["is_dir"]:
                    shutil.rmtree(game["rom_abs_path"])
                else:
                    os.remove(game["rom_abs_path"])

            if game.get("cover_abs_path") and os.path.exists(game["cover_abs_path"]):
                try:
                    os.remove(game["cover_abs_path"])
                except Exception:
                    pass

            sys_path = os.path.join(self.roms_root, system_id)
            gamelist_path = os.path.join(sys_path, "gamelist.xml")
            if os.path.exists(gamelist_path):
                tree = ET.parse(gamelist_path)
                root = tree.getroot()
                target_path_1 = f"./{game['filename']}".lower()
                target_path_2 = f"./{game.get('main_file', '')}".lower()
                for g_elem in list(root.findall('game')):
                    p = g_elem.find('path')
                    if p is not None and p.text:
                        p_norm = p.text.strip().lower().replace('\\', '/')
                        if p_norm in (target_path_1, target_path_2, game['filename'].lower()) or (game["is_dir"] and p_norm.startswith(target_path_1 + "/")):
                            root.remove(g_elem)
                self._save_gamelist_tree(tree, system_id, sys_path)

            self._clear_cache_for_system(system_id)
            if token in self.token_registry:
                del self.token_registry[token]

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_uploaded_rom(self, system_id, filename, file_bytes=None, display_name=None, is_folder=False, folder_name=None, cover_bytes=None, cover_ext=".png", temp_file_path=None):
        """Save newly uploaded ROM file into system directory and update gamelist.xml."""
        sys_path = os.path.join(self.roms_root, system_id)
        if not os.path.exists(sys_path):
            os.makedirs(sys_path, exist_ok=True)

        if is_folder and folder_name:
            target_dir = os.path.join(sys_path, folder_name)
            os.makedirs(target_dir, exist_ok=True)
            safe_rel_filename = filename.replace('\\', '/').lstrip('/')
            target_file_path = os.path.join(target_dir, safe_rel_filename)
            os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
            entry_name = folder_name
        else:
            target_file_path = os.path.join(sys_path, filename)
            entry_name = filename

        try:
            if temp_file_path and os.path.exists(temp_file_path):
                # Efficient move across filesystem (instant atomic rename, 0 RAM usage)
                shutil.move(temp_file_path, target_file_path)
            elif file_bytes is not None:
                with open(target_file_path, 'wb') as f:
                    f.write(file_bytes)
            else:
                return {"success": False, "error": "No ROM file data provided"}

            clean_display = display_name if (display_name and display_name.strip()) else os.path.splitext(entry_name)[0]
            gamelist_path = os.path.join(sys_path, "gamelist.xml")
            if os.path.exists(gamelist_path):
                tree = ET.parse(gamelist_path)
                root = tree.getroot()
            else:
                root = ET.Element("gameList")
                tree = ET.ElementTree(root)

            target_path = f"./{entry_name}".lower()
            found = False
            target_elem = None
            for g_elem in root.findall('game'):
                p = g_elem.find('path')
                if p is not None and p.text and p.text.strip().lower() == target_path:
                    found = True
                    target_elem = g_elem
                    n = g_elem.find('name')
                    if n is not None:
                        n.text = clean_display
                    break

            if not found:
                target_elem = ET.SubElement(root, 'game')
                p = ET.SubElement(target_elem, 'path')
                p.text = f"./{entry_name}"
                n = ET.SubElement(target_elem, 'name')
                n.text = clean_display

            # If cover bytes provided, save cover image and link in XML
            if cover_bytes:
                images_dir = os.path.join(sys_path, "images")
                os.makedirs(images_dir, exist_ok=True)
                base_name = os.path.splitext(entry_name)[0]
                cover_filename = f"{base_name}-image{cover_ext}"
                cover_abs_path = os.path.join(images_dir, cover_filename)
                with open(cover_abs_path, 'wb') as cf:
                    cf.write(cover_bytes)

                img_elem = target_elem.find('image')
                if img_elem is None:
                    img_elem = ET.SubElement(target_elem, 'image')
                img_elem.text = f"./images/{cover_filename}"

            self._save_gamelist_tree(tree, system_id, sys_path)
            self._clear_cache_for_system(system_id)

            return {"success": True, "filename": entry_name, "display_name": clean_display}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ================= Save Manager (Premium) =================
    def list_all_saves(self):
        """Scans all system directories for game save files (.sav, .srm, .state*)."""
        saves = []
        systems = self.list_systems(is_premium=True, include_empty=True)

        for sys_info in systems:
            sys_id = sys_info["id"]
            sys_path = sys_info["path"]
            if not os.path.exists(sys_path):
                continue

            try:
                files = os.listdir(sys_path)
            except Exception:
                continue

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in SAVE_EXTENSIONS:
                    f_path = os.path.join(sys_path, f)
                    if os.path.isfile(f_path):
                        base_name = os.path.splitext(f)[0]
                        size_bytes = os.path.getsize(f_path)
                        mtime = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(f_path)))

                        # Check if game has a cover
                        has_cover = False
                        cover_url = ""
                        for img_dir in ['images', 'boxart']:
                            for img_ext in ['.png', '.jpg']:
                                test_c = os.path.join(sys_path, img_dir, f"{base_name}-image{img_ext}")
                                if os.path.exists(test_c):
                                    has_cover = True
                                    cover_url = f"/api/image?system={sys_id}&path=./{img_dir}/{os.path.basename(test_c)}"
                                    break
                            if has_cover:
                                break

                        saves.append({
                            "system": sys_id,
                            "system_name": sys_info["name"],
                            "filename": f,
                            "game_title": base_name,
                            "size_str": self._format_size(size_bytes),
                            "modified": mtime,
                            "cover_url": cover_url
                        })

        return sorted(saves, key=lambda x: (x["system"], x["game_title"]))

    def delete_save_file(self, system_id, filename):
        """Deletes a save file safely."""
        sys_path = os.path.join(self.roms_root, system_id)
        f_path = os.path.join(sys_path, filename)
        ext = os.path.splitext(filename)[1].lower()

        if ext not in SAVE_EXTENSIONS:
            return {"success": False, "error": "Not a valid save file extension"}

        if os.path.exists(f_path) and os.path.isfile(f_path):
            try:
                os.remove(f_path)
                self._clear_cache_for_system(system_id)
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "Save file not found"}

    def backup_all_saves_zip(self):
        """Creates an in-memory zip containing all save files from all systems."""
        buf = io.BytesIO()
        saves_found = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for sys_info in self.list_systems(is_premium=True):
                sys_id = sys_info["id"]
                sys_path = sys_info["path"]
                if not os.path.exists(sys_path):
                    continue
                try:
                    for f in os.listdir(sys_path):
                        ext = os.path.splitext(f)[1].lower()
                        if ext in SAVE_EXTENSIONS:
                            full_p = os.path.join(sys_path, f)
                            if os.path.isfile(full_p):
                                arc_name = f"{sys_id}/{f}"
                                z.write(full_p, arc_name)
                                saves_found += 1
                except Exception:
                    pass

        buf.seek(0)
        return buf.read(), saves_found

    # ================= Cheat Manager (Premium) =================
    def get_cheats_for_game(self, token):
        """Reads RetroArch .cht file for a given game."""
        game = self.get_game_by_token(token)
        if not game:
            return {"success": False, "error": "Game not found"}

        cht_path = self._find_cheat_file(game["system"], game["filename"])
        if not cht_path or not os.path.exists(cht_path):
            return {"success": True, "cheats": [], "has_file": False, "game": game["display_name"]}

        try:
            with open(cht_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            cheats = self._parse_cht(content)
            return {
                "success": True,
                "cheats": cheats,
                "has_file": True,
                "filename": os.path.basename(cht_path),
                "game": game["display_name"]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_cheats_for_game(self, token, updated_cheats):
        """Writes updated cheat toggles back to .cht file."""
        game = self.get_game_by_token(token)
        if not game:
            return {"success": False, "error": "Game not found"}

        system_id = game["system"]
        sys_cheats_dir = os.path.join(self.cheats_dir, system_id)
        os.makedirs(sys_cheats_dir, exist_ok=True)

        base_name = os.path.splitext(game["filename"])[0]
        cht_path = os.path.join(sys_cheats_dir, f"{base_name}.cht")

        try:
            content = self._serialize_cht(updated_cheats)
            with open(cht_path, 'w', encoding='utf-8') as f:
                f.write(content)

            self._clear_cache_for_system(system_id)
            return {"success": True, "cheat_count": len(updated_cheats)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def upload_cheat_zip(self, zip_bytes):
        """Extracts a zip file of RetroArch cheats into /roms/cheats/."""
        try:
            buf = io.BytesIO(zip_bytes)
            extracted_count = 0
            with zipfile.ZipFile(buf, 'r') as z:
                for file_info in z.infolist():
                    if file_info.filename.endswith('/') or not file_info.filename.endswith('.cht'):
                        continue
                    clean_name = os.path.normpath(file_info.filename).lstrip(os.sep)
                    target_path = os.path.join(self.cheats_dir, clean_name)
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with z.open(file_info) as src, open(target_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    extracted_count += 1

            self.cache.clear()
            return {"success": True, "count": extracted_count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _parse_cht(self, text):
        """Parses RetroArch .cht file format."""
        cheats = []
        current = None
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip().lower()
                v = v.strip().strip('"\'')
                if "_desc" in k:
                    current = {"desc": v, "code": "", "enable": False}
                    cheats.append(current)
                elif "_code" in k and current is not None:
                    current["code"] = v
                elif "_enable" in k and current is not None:
                    current["enable"] = (v.lower() == "true" or v == "1")
        return cheats

    def _serialize_cht(self, cheats):
        """Serializes list of cheats into RetroArch .cht format."""
        lines = [f"cheats = {len(cheats)}\n"]
        for i, c in enumerate(cheats):
            desc = c.get("desc", f"Cheat {i+1}")
            code = c.get("code", "")
            enable = "true" if c.get("enable") else "false"
            lines.append(f'cheat{i}_desc = "{desc}"')
            lines.append(f'cheat{i}_code = "{code}"')
            lines.append(f'cheat{i}_enable = {enable}\n')
        return "\n".join(lines)

    def _clear_cache_for_system(self, system_id):
        keys_to_del = [k for k in self.cache if k.startswith(system_id)]
        for k in keys_to_del:
            del self.cache[k]

    def _format_size(self, size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{round(size_bytes / 1024, 1)} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{round(size_bytes / (1024 * 1024), 1)} MB"
        else:
            return f"{round(size_bytes / (1024 * 1024 * 1024), 2)} GB"
