import sys
import io
import time
import webbrowser
import threading

# Ensure UTF-8 output on Windows console
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

from app import app

def open_browser():
    time.sleep(1.2)
    webbrowser.open('http://localhost:5000')

if __name__ == '__main__':
    print("=" * 65)
    print("  ArkOS WiFi ROM & Cover Manager")
    print("  -------------------------------------------------------------")
    print("  Server is starting...")
    print("  Open browser at: http://localhost:5000")
    print("=" * 65)

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
