# backend/launcher_host.py
import sys
import json
import struct
import subprocess
import os
import urllib.request

# Read a message from stdin and decode it.
def read_message():
    try:
        raw_length = sys.stdin.buffer.read(4)
        if len(raw_length) == 0:
            sys.exit(0)
        message_length = struct.unpack('@I', raw_length)[0]
        message = sys.stdin.buffer.read(message_length).decode('utf-8')
        return json.loads(message)
    except Exception:
        sys.exit(0)

# Encode a message and write it to stdout.
def send_message(message):
    try:
        encoded_message = json.dumps(message).encode('utf-8')
        sys.stdout.buffer.write(struct.pack('@I', len(encoded_message)))
        sys.stdout.buffer.write(encoded_message)
        sys.stdout.buffer.flush()
    except Exception:
        sys.exit(0)

def is_server_port_active() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False

def main():
    while True:
        msg = read_message()
        action = msg.get("action")
        
        if action == "start":
            launcher_path = msg.get("launcher_path")
            if not launcher_path or not os.path.exists(launcher_path):
                send_message({"status": "error", "message": "Backend launcher not found"})
                continue
                
            if is_server_port_active():
                send_message({"status": "success", "message": "Server already active"})
                continue
                
            try:
                # Start detached process
                subprocess.Popen(
                    ["cmd.exe", "/c", launcher_path],
                    cwd=os.path.dirname(launcher_path),
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                )
                send_message({"status": "success", "message": "Backend start initiated"})
            except Exception as e:
                send_message({"status": "error", "message": str(e)})
                
        elif action == "stop":
            if not is_server_port_active():
                send_message({"status": "success", "message": "Server already stopped"})
                continue
                
            try:
                req = urllib.request.Request("http://127.0.0.1:8000/api/shutdown", method="POST")
                with urllib.request.urlopen(req, timeout=2) as r:
                    pass
                send_message({"status": "success", "message": "Backend stop initiated"})
            except Exception as e:
                # Fallback to killing pythonw.exe if API shutdown fails
                try:
                    subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
                    send_message({"status": "success", "message": "Force stopped pythonw"})
                except Exception as ex:
                    send_message({"status": "error", "message": f"Failed to stop: {e} and {ex}"})
                    
        elif action == "status":
            active = is_server_port_active()
            send_message({"status": "running" if active else "stopped"})
            
        else:
            send_message({"status": "error", "message": "Unknown action"})

if __name__ == "__main__":
    main()
