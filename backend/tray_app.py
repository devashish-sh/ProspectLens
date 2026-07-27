# backend/tray_app.py
# ProspectLens — System Tray Launcher & Server Controller
#
# Step 12: Desktop integration running a Pystray tray icon.
# Starts uvicorn server as a background subprocess, offering Start/Stop controls.

import os
import sys
import subprocess
import webbrowser
import time
import urllib.request
import urllib.error
from pathlib import Path
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

# Global subprocess reference
server_process = None
tray_icon = None

def get_icon_image():
    """Loads the rebranded icon or creates a fallback pillow image if missing."""
    if ICON_PATH.exists():
        try:
            return Image.open(ICON_PATH)
        except Exception as e:
            print(f"Error loading icon image: {e}")
            
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
    """Returns True if the uvicorn subprocess is alive or the port is already active."""
    global server_process
    if server_process and server_process.poll() is None:
        return True
    return is_server_port_active()

def start_server():
    """Spins up uvicorn server in a subprocess."""
    global server_process
    if is_server_running():
        print("Server is already running.")
        return

    print("Starting uvicorn server...")
    
    # Run uvicorn using the virtualenv python interpreter
    # Port 8000 matches all popup.js/dashboard.js config
    command = [
        str(VENV_PYTHON),
        "-m", "uvicorn",
        "main:app",
        "--host", "127.0.0.1",
        "--port", "8000"
    ]
    
    try:
        # Start uvicorn with stdout/stderr hidden to avoid console windows popping up on Windows
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        server_process = subprocess.Popen(
            command,
            cwd=str(ROOT_DIR),
            startupinfo=startupinfo
        )
        print(f"Uvicorn server spawned (PID: {server_process.pid})")
    except Exception as e:
        print(f"Failed to start server: {e}")

def stop_server():
    """Terminates uvicorn server subprocess."""
    global server_process
    if server_process:
        print("Stopping spawned uvicorn server...")
        if os.name == 'nt':
            # Force terminate subprocess tree on Windows
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(server_process.pid)], capture_output=True)
        else:
            server_process.terminate()
        server_process = None
        print("Uvicorn server stopped.")
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
