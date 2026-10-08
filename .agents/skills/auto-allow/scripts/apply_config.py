import os
import sys
import json
import shutil

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CONFIG_FILE = r'C:\Users\PANGBALL\.gemini\config\config.json'
CLI_SETTINGS_DIR = r'C:\Users\PANGBALL\.gemini\antigravity-cli'
CLI_SETTINGS_FILE = os.path.join(CLI_SETTINGS_DIR, 'settings.json')

def apply():
    print("=====================================================")
    print("  Antigravity Auto-Allow & Permission Configurator   ")
    print("=====================================================")
    
    # 1. Update ~/.gemini/config/config.json
    if os.path.exists(CONFIG_FILE):
        bak_file = CONFIG_FILE + ".bak"
        if not os.path.exists(bak_file):
            shutil.copy2(CONFIG_FILE, bak_file)
            print(f"[OK] Created backup: {bak_file}")
            
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        us = data.setdefault('userSettings', {})
        us['toolExecutionPolicy'] = 'always-proceed'
        us['autoExecutionPolicy'] = 'always-proceed'
        us['nonWorkspaceFileAccess'] = 'allow'
        us['internetAccessPolicy'] = 'allow'
        
        gpg = us.setdefault('globalPermissionGrants', {})
        allow_list = gpg.setdefault('allow', [])
        
        wildcards = [
            'command(*)',
            'read_file(*)',
            'write_file(*)',
            'edit_file(*)',
            'run_command(*)',
            'search_web(*)',
            'read_url_content(*)',
            '*'
        ]
        
        for w in reversed(wildcards):
            if w not in allow_list:
                allow_list.insert(0, w)
                
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        print(f"[OK] Successfully injected wildcard permissions into config.json!")
        print(f"    - toolExecutionPolicy: always-proceed")
        print(f"    - nonWorkspaceFileAccess: allow")
        print(f"    - Added wildcards: {wildcards}")

    # 2. Update ~/.gemini/antigravity-cli/settings.json
    os.makedirs(CLI_SETTINGS_DIR, exist_ok=True)
    cli_data = {}
    if os.path.exists(CLI_SETTINGS_FILE):
        try:
            with open(CLI_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                cli_data = json.load(f)
        except Exception:
            pass
            
    cli_data['toolPermission'] = 'always-proceed'
    cli_data['enableTerminalSandbox'] = False
    trusted = cli_data.setdefault('trustedWorkspaces', [])
    for p in [r"C:\Users\PANGBALL", r"C:\Users\PANGBALL\.gemini\antigravity\scratch\ArkOS-WiFi-Manager"]:
        if p not in trusted:
            trusted.append(p)
            
    with open(CLI_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(cli_data, f, indent=2)
        
    print(f"[OK] Successfully configured CLI settings.json with toolPermission='always-proceed'")
    print("=====================================================")
    print(" Auto-Allow is now FULLY CONFIGURED!")
    print("=====================================================")

def restore():
    print("=====================================================")
    print("  Restoring Antigravity Permissions from Backup      ")
    print("=====================================================")
    bak_file = CONFIG_FILE + ".bak"
    if os.path.exists(bak_file):
        shutil.copy2(bak_file, CONFIG_FILE)
        print(f"[OK] Restored original config from {bak_file}")
    else:
        print("[!] No backup file found.")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--restore':
        restore()
    else:
        apply()
