import os
import json
import re
import urllib.parse
import requests
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
    """Removes dump tags like (USA), [!], (v1.1), (Japan) for cleaner search"""
    t = re.sub(r'\(.*?\)', '', title)
    t = re.sub(r'\[.*?\]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def get_system_boxart_list(repo_name: str) -> List[str]:
    """Gets list of all available box arts in a Libretro repo (with disk caching)"""
    cache_file = os.path.join(CACHE_DIR, f"{repo_name}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    # Fetch from GitHub API
    url = f"https://api.github.com/repos/libretro-thumbnails/{repo_name}/git/trees/master?recursive=1"
    headers = {'User-Agent': 'ArkOS-WiFi-Manager/1.0'}
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            tree = res.json().get('tree', [])
            boxarts = [
                item['path'].replace('Named_Boxarts/', '')
                for item in tree
                if item['path'].startswith('Named_Boxarts/') and item['path'].endswith('.png')
            ]
            # Save to disk cache
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(boxarts, f, ensure_ascii=False)
            return boxarts
    except Exception as e:
        print(f"Error fetching repo list for {repo_name}:", e)
    return []

def search_box_arts(query: str, system_id: str = "") -> List[Dict[str, str]]:
    """Searches Libretro thumbnails repository for high quality game box arts"""
    results = []
    repo_name = LIBRETRO_REPOS.get(system_id.lower())
    
    clean_q = clean_game_title(query).lower()
    keywords = [k for k in re.split(r'[\s_:-]+', clean_q) if len(k) > 1]
    
    if not repo_name:
        # If system is unknown or arcade, search GBA or fallback
        repo_name = "Nintendo_-_Game_Boy_Advance"

    boxarts = get_system_boxart_list(repo_name)

    if boxarts and keywords:
        scored_matches = []
        for filename in boxarts:
            name_lower = filename.lower()
            # Calculate match score
            score = 0
            # Exact phrase match
            if clean_q in name_lower:
                score += 50
            # Keyword matches
            matched_words = sum(1 for kw in keywords if kw in name_lower)
            if matched_words == len(keywords):
                score += 30
            elif matched_words > 0:
                score += matched_words * 5

            if score > 0:
                # Prioritize USA or Europe versions
                if '(usa' in name_lower or '(europe' in name_lower:
                    score += 5
                scored_matches.append((score, filename))

        scored_matches.sort(key=lambda x: -x[0])

        for score, filename in scored_matches[:16]:
            clean_display = filename[:-4]  # Remove .png
            encoded_fn = urllib.parse.quote(filename)
            raw_url = f"https://raw.githubusercontent.com/libretro-thumbnails/{repo_name}/master/Named_Boxarts/{encoded_fn}"
            
            results.append({
                "title": clean_display,
                "image_url": raw_url,
                "thumbnail": raw_url,
                "source": "Libretro Official Database"
            })

    return results

def download_image_bytes(url: str) -> bytes:
    """Downloads an image from URL and returns bytes"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r.content
