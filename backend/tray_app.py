# backend/tray_app.py
# ProspectLens — System Tray Launcher & Server Controller
#
# Step 12: Desktop integration running a Pystray tray icon.
# Starts uvicorn server as a background subprocess, offering Start/Stop controls.

import os
import sys
import time
from pathlib import Path

# Setup logging directory and file redirect immediately to prevent crashes on sys.stdout/sys.stderr being None in windowless mode
def get_log_file():
    paths_to_try = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        paths_to_try.append(Path(local_app_data) / "ProspectLens" / "logs" / "engine.log")
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        paths_to_try.append(Path(user_profile) / "AppData" / "Local" / "ProspectLens" / "logs" / "engine.log")
    try:
        paths_to_try.append(Path.home() / "AppData" / "Local" / "ProspectLens" / "logs" / "engine.log")
    except Exception:
        pass
    try:
        import tempfile
        paths_to_try.append(Path(tempfile.gettempdir()) / "ProspectLens" / "engine.log")
    except Exception:
        pass
    for p in paths_to_try:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write("")
            return p
        except Exception:
            continue
    return None

class SafeWriter:
    def __init__(self, file_path):
        self.file = None
        if file_path:
            try:
                self.file = open(file_path, "a", encoding="utf-8", buffering=1)
            except Exception:
                pass
    def write(self, data):
        if self.file:
            try:
                self.file.write(data)
            except Exception:
                pass
    def flush(self):
        if self.file:
            try:
                self.file.flush()
            except Exception:
                pass

log_file = get_log_file()
safe_writer = SafeWriter(log_file)
sys.stdout = safe_writer
sys.stderr = safe_writer
print(f"\n--- ProspectLens Log Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

# Now import other modules safely after stdout/stderr redirection
import subprocess
import webbrowser
import urllib.request
import urllib.error
import threading
from PIL import Image
import pystray
from pystray import MenuItem as item

# Absolute path configurations
ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
ICON_PATH = PROJECT_ROOT / "extension" / "icons" / "icon32.png"
VENV_PYTHON = ROOT_DIR / "venv" / "Scripts" / "python.exe"

# If running outside venv or virtual environment python doesn't exist, fallback to sys.executable
if not VENV_PYTHON.exists():
    VENV_PYTHON = sys.executable

# Global server references
server_instance = None
server_thread = None
tray_icon = None

import uvicorn
class ProgrammaticServer(uvicorn.Server):
    def install_signal_handlers(self):
        pass

def get_icon_image():
    """Loads the branded ProspectLens icon or creates a fallback pillow image if missing."""
    possible_paths = []
    
    # 1. PyInstaller bundled resources
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            possible_paths.append(Path(sys._MEIPASS) / "icons" / "icon32.png")
            possible_paths.append(Path(sys._MEIPASS) / "icons" / "icon128.png")
        possible_paths.append(Path(sys.executable).parent / "_internal" / "icons" / "icon32.png")
        possible_paths.append(Path(sys.executable).parent / "icons" / "icon32.png")
    
    # 2. Local project directories
    possible_paths.append(ROOT_DIR / "icons" / "icon32.png")
    possible_paths.append(ROOT_DIR / "icons" / "icon128.png")
    possible_paths.append(ICON_PATH)
    possible_paths.append(PROJECT_ROOT / "extension" / "icons" / "icon32.png")
    possible_paths.append(PROJECT_ROOT / "extension" / "icons" / "icon128.png")

    for p in possible_paths:
        if p and p.exists():
            try:
                return Image.open(p)
            except Exception as e:
                print(f"Error loading icon image from {p}: {e}")
            
    # Fallback placeholder image
    img = Image.new("RGBA", (32, 32), color=(31, 32, 31, 255))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.ellipse((6, 6, 26, 26), fill=(118, 165, 68, 255))
    return img

def is_server_port_active() -> bool:
    """Checks if the backend API is already listening on port 8000."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False

def is_server_running() -> bool:
    """Returns True if the uvicorn thread is active or the port is already active."""
    global server_instance
    if server_instance and not server_instance.should_exit:
        return True
    return is_server_port_active()

def start_server():
    """Spins up uvicorn server programmatically in a daemon thread."""
    global server_instance, server_thread
    if is_server_running():
        print("Server is already running.")
        return

    print("Starting programmatic uvicorn server...")
    
    # Ensure root directory is in sys.path
    sys.path.insert(0, str(ROOT_DIR))
    from main import app
    
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        log_config=None
    )
    
    try:
        server_instance = ProgrammaticServer(config=config)
        server_thread = threading.Thread(target=server_instance.run, daemon=True)
        server_thread.start()
        print("Programmatic Uvicorn server thread started successfully.")
    except Exception as e:
        print(f"Failed to start programmatic server: {e}")

def stop_server():
    """Terminates programmatically run uvicorn server."""
    global server_instance
    if server_instance:
        print("Stopping programmatic uvicorn server...")
        server_instance.should_exit = True
        server_instance = None
        print("Uvicorn server stop requested.")
    else:
        # If the server is running on the port but was not spawned in this session,
        # request shutdown via the shutdown API.
        if is_server_port_active():
            print("Requesting shutdown of active server on port 8000...")
            try:
                req = urllib.request.Request("http://127.0.0.1:8000/api/shutdown", method="POST")
                with urllib.request.urlopen(req, timeout=2) as r:
                    print("Shutdown requested successfully:", r.read().decode())
            except Exception as e:
                print(f"Failed to request API shutdown: {e}")

def menu_status_text(item):
    """Dynamically displays status label in tray menu."""
    if is_server_running():
        return "Status: Online (Port 8000)"
    return "Status: Offline"

def on_start(icon, item):
    start_server()

def on_stop(icon, item):
    stop_server()

def on_open_dashboard(icon, item):
    webbrowser.open("http://localhost:8000/docs")

def on_exit(icon, item):
    # Closes the system tray app, but does NOT stop the server process.
    # The server process will continue running in the background.
    print("Exiting tray interface. Server process left running.")
    icon.stop()

def setup_tray():
    """Configures pystray menu item layout and starts event loop."""
    global tray_icon
    
    menu = pystray.Menu(
        item(menu_status_text, lambda icon: None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("Start Server", on_start, enabled=lambda item: not is_server_running()),
        item("Stop Server", on_stop, enabled=lambda item: is_server_running()),
        pystray.Menu.SEPARATOR,
        item("Open API Docs", on_open_dashboard, enabled=lambda item: is_server_running()),
        item("Exit", on_exit)
    )

    tray_icon = pystray.Icon(
        name="prospectlens",
        title="ProspectLens Backend Control",
        icon=get_icon_image(),
        menu=menu
    )
    
    # Auto-start server when launching the tray application
    start_server()
    
    # Block and run tray loop
    tray_icon.run()

if __name__ == "__main__":
    setup_tray()
