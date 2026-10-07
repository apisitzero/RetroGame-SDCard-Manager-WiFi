# -*- coding: utf-8 -*-
"""
Zero-dependency Box Art Scraper for ArkOS
Fetches thumbnails directly from Libretro GitHub repository indexes.
Created for: เพจเล่าเรื่องเกม (Lao Reuang Game)
"""

import os
import json
import re
import urllib.request
import urllib.parse
from typing import List, Dict

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache_boxarts")
os.makedirs(CACHE_DIR, exist_ok=True)

# Mapping between ArkOS system names and Libretro thumbnail repositories
LIBRETRO_REPOS = {
    "gba": "Nintendo_-_Game_Boy_Advance",
    "gb": "Nintendo_-_Game_Boy",
    "gbc": "Nintendo_-_Game_Boy_Color",
    "sfc": "Nintendo_-_Super_Nintendo_Entertainment_System",
    "snes": "Nintendo_-_Super_Nintendo_Entertainment_System",
    "nes": "Nintendo_-_Nintendo_Entertainment_System",
    "fc": "Nintendo_-_Nintendo_Entertainment_System",
    "n64": "Nintendo_-_Nintendo_64",
    "nds": "Nintendo_-_Nintendo_DS",
    "psx": "Sony_-_PlayStation",
    "ps1": "Sony_-_PlayStation",
    "psp": "Sony_-_PlayStation_Portable",
    "megadrive": "Sega_-_Mega_Drive_-_Genesis",
    "genesis": "Sega_-_Mega_Drive_-_Genesis",
    "mastersystem": "Sega_-_Master_System_-_Mark_III",
    "gamegear": "Sega_-_Game_Gear",
    "dreamcast": "Sega_-_Dreamcast",
    "saturn": "Sega_-_Saturn",
    "sega32x": "Sega_-_32X",
    "segacd": "Sega_-_Mega-CD_-_Sega_CD",
    "pce": "NEC_-_PC_Engine_-_TurboGrafx_16",
    "pcecd": "NEC_-_PC_Engine_CD_-_TurboGrafx-CD",
    "neogeo": "SNK_-_Neo_Geo",
    "atari2600": "Atari_-_2600",
    "atari7800": "Atari_-_7800",
    "lynx": "Atari_-_Lynx",
    "wonderswan": "Bandai_-_WonderSwan",
    "fbneo": "FBNeo_-_Arcade_Games",
    "mame": "MAME"
}

def clean_game_title(title: str) -> str:
    """Removes dump tags like (USA), [!], (v1.1), (Japan) for cleaner search."""
    t = re.sub(r'\(.*?\)', '', title)
    t = re.sub(r'\[.*?\]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def get_system_boxart_list(repo_name: str) -> List[str]:
    """Gets list of all available box arts in a Libretro repo (with local JSON caching)."""
    cache_file = os.path.join(CACHE_DIR, f"{repo_name}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    # Fetch from GitHub API using urllib
    url = f"https://api.github.com/repos/libretro-thumbnails/{repo_name}/git/trees/master?recursive=1"
    req = urllib.request.Request(url, headers={'User-Agent': 'ArkOS-WiFi-Manager/2.0'})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                tree = data.get('tree', [])
                boxarts = [
                    item['path'].replace('Named_Boxarts/', '')
                    for item in tree
                    if item['path'].startswith('Named_Boxarts/') and item['path'].endswith('.png')
                ]
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(boxarts, f, ensure_ascii=False)
                return boxarts
    except Exception as e:
        print(f"[Scraper] Error fetching repo list for {repo_name}: {e}")
    return []

def search_box_arts(query: str, system_id: str = "") -> List[Dict[str, str]]:
    """Searches Libretro thumbnails repository for high quality game box arts."""
    results = []
    repo_name = LIBRETRO_REPOS.get(system_id.lower())
    
    clean_q = clean_game_title(query).lower()
    keywords = [k for k in re.split(r'[\s_:-]+', clean_q) if len(k) > 1]
    
    if not repo_name:
        repo_name = "Nintendo_-_Game_Boy_Advance"

    boxarts = get_system_boxart_list(repo_name)

    if boxarts and keywords:
        scored_matches = []
        for filename in boxarts:
            name_lower = filename.lower()
            score = 0
            if clean_q in name_lower:
                score += 50
            matched_words = sum(1 for kw in keywords if kw in name_lower)
            if matched_words == len(keywords):
                score += 30
            elif matched_words > 0:
                score += matched_words * 5

            if score > 0:
                if '(usa' in name_lower or '(europe' in name_lower:
                    score += 5
                scored_matches.append((score, filename))

        scored_matches.sort(key=lambda x: -x[0])

        for score, filename in scored_matches[:16]:
            clean_display = filename[:-4]
            encoded_path = urllib.parse.quote(filename)
            raw_url = f"https://raw.githubusercontent.com/libretro-thumbnails/{repo_name}/master/Named_Boxarts/{encoded_path}"
            results.append({
                "title": clean_display,
                "filename": filename,
                "url": raw_url,
                "source": "Libretro"
            })

    return results

def download_image_bytes(image_url: str) -> bytes:
    """Download image bytes from external URL."""
    req = urllib.request.Request(image_url, headers={'User-Agent': 'ArkOS-WiFi-Manager/2.0'})
    with urllib.request.urlopen(req, timeout=12) as response:
        return response.read()
