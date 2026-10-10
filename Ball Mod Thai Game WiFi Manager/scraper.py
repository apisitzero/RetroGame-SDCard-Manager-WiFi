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

def normalize_text(s: str) -> str:
    """Normalize text by stripping quotes, hyphens, and punctuation for fuzzy matching."""
    s = re.sub(r"['\"`\.\-_,:;!?/]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()

def get_system_boxart_list(repo_name: str) -> List[str]:
    """Gets list of all available box arts in a Libretro repo (with local JSON caching & 2-step GitHub lookup)."""
    cache_file = os.path.join(CACHE_DIR, f"{repo_name}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
                if cached and isinstance(cached, list):
                    return cached
        except Exception:
            pass

    headers = {'User-Agent': 'ArkOS-WiFi-Manager/2.0'}

    # Strategy 1: 2-step tree lookup (Works reliably on massive repos like Sony_-_PlayStation without HTTP 500)
    try:
        root_url = f"https://api.github.com/repos/libretro-thumbnails/{repo_name}/git/trees/master"
        req = urllib.request.Request(root_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                root_data = json.loads(response.read().decode('utf-8'))
                boxarts_sha = None
                for item in root_data.get('tree', []):
                    if item.get('path') == 'Named_Boxarts' and item.get('type') == 'tree':
                        boxarts_sha = item.get('sha')
                        break

                if boxarts_sha:
                    sub_url = f"https://api.github.com/repos/libretro-thumbnails/{repo_name}/git/trees/{boxarts_sha}"
                    sub_req = urllib.request.Request(sub_url, headers=headers)
                    with urllib.request.urlopen(sub_req, timeout=12) as sub_resp:
                        if sub_resp.status == 200:
                            sub_data = json.loads(sub_resp.read().decode('utf-8'))
                            boxarts = [
                                item['path']
                                for item in sub_data.get('tree', [])
                                if item.get('path', '').endswith('.png')
                            ]
                            if boxarts:
                                with open(cache_file, 'w', encoding='utf-8') as f:
                                    json.dump(boxarts, f, ensure_ascii=False)
                                return boxarts
    except Exception as e:
        print(f"[Scraper] 2-step tree lookup failed for {repo_name}: {e}")

    # Strategy 2: Recursive lookup fallback for smaller repos
    try:
        url = f"https://api.github.com/repos/libretro-thumbnails/{repo_name}/git/trees/master?recursive=1"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                tree = data.get('tree', [])
                boxarts = [
                    item['path'].replace('Named_Boxarts/', '')
                    for item in tree
                    if item.get('path', '').startswith('Named_Boxarts/') and item.get('path', '').endswith('.png')
                ]
                if boxarts:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(boxarts, f, ensure_ascii=False)
                    return boxarts
    except Exception as e:
        print(f"[Scraper] Recursive lookup failed for {repo_name}: {e}")

    return []

def search_box_arts(query: str, system_id: str = "") -> List[Dict[str, str]]:
    """Searches Libretro thumbnails repository for high quality game box arts."""
    results = []
    repo_name = LIBRETRO_REPOS.get(system_id.lower())
    
    clean_q = clean_game_title(query)
    norm_q = normalize_text(clean_q)
    keywords = [k for k in norm_q.split() if len(k) > 1]
    
    if not repo_name:
        repo_name = "Nintendo_-_Game_Boy_Advance"

    boxarts = get_system_boxart_list(repo_name)

    if boxarts and keywords:
        scored_matches = []
        for filename in boxarts:
            name_no_ext = filename[:-4] if filename.endswith('.png') else filename
            norm_name = normalize_text(name_no_ext)
            score = 0

            # Exact or prefix normalized match
            if norm_q in norm_name:
                score += 50
            if norm_name.startswith(norm_q):
                score += 25

            matched_words = sum(1 for kw in keywords if kw in norm_name)
            if matched_words == len(keywords):
                score += 30
            elif matched_words > 0:
                score += matched_words * 5

            if score > 0:
                fn_lower = filename.lower()
                if '(usa' in fn_lower or '(europe' in fn_lower:
                    score += 5
                if '(japan' in fn_lower and '(japan' not in query.lower():
                    score -= 2
                scored_matches.append((score, filename))

        scored_matches.sort(key=lambda x: -x[0])

        for score, filename in scored_matches[:20]:
            clean_display = filename[:-4] if filename.endswith('.png') else filename
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
