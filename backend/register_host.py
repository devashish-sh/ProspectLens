# backend/register_host.py
import os
import sys
import json
import base64
import hashlib
import winreg
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def setup_native_messaging():
    project_root = Path(__file__).resolve().parent.parent
    backend_dir = project_root / "backend"
    manifest_path = project_root / "extension" / "manifest.json"
    key_file = backend_dir / "extension_key.pem"

    print("[Setup] Configuring Native Messaging Host...")

    # 1. Generate or load RSA private key
    if not key_file.exists():
        print("[Setup] Generating new RSA keypair...")
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        with open(key_file, "wb") as f:
            f.write(pem)
    else:
        print("[Setup] Loading existing RSA keypair...")
        with open(key_file, "rb") as f:
            pem = f.read()
        private_key = serialization.load_pem_private_key(pem, password=None)

    # 2. Extract public key DER bytes
    public_key = private_key.public_key()
    der_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    b64_key = base64.b64encode(der_bytes).decode("utf-8")

    # 3. Calculate Chrome Extension ID
    sha256_hash = hashlib.sha256(der_bytes).hexdigest()[:32]
    translation_table = str.maketrans("0123456789abcdef", "abcdefghijklmnop")
    extension_id = sha256_hash.translate(translation_table)
    print(f"[Setup] Target Chrome Extension ID: {extension_id}")

    # 4. Update manifest.json with key
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        # Add key to manifest
        manifest["key"] = b64_key
        
        # Ensure nativeMessaging is in permissions
        if "permissions" not in manifest:
            manifest["permissions"] = []
        if "nativeMessaging" not in manifest["permissions"]:
            manifest["permissions"].append("nativeMessaging")
            print("[Setup] Added 'nativeMessaging' permission to manifest.json")
            
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        print("[Setup] Updated manifest.json with fixed extension key.")
    else:
        print("[Setup] Error: manifest.json not found!")
        return

    # 5. Create launcher_host.bat
    host_bat_path = backend_dir / "launcher_host.bat"
    bat_content = f'@echo off\n"{backend_dir}\\venv\\Scripts\\python.exe" "{backend_dir}\\launcher_host.py" %*\n'
    with open(host_bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print(f"[Setup] Created launcher batch file: {host_bat_path}")

    # 6. Create Native Host Manifest JSON
    host_manifest_path = backend_dir / "com.prospectlens.launcher.json"
    host_manifest = {
        "name": "com.prospectlens.launcher",
        "description": "ProspectLens Backend Launcher Host",
        "path": str(host_bat_path),
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{extension_id}/"
        ]
    }
    with open(host_manifest_path, "w", encoding="utf-8") as f:
        json.dump(host_manifest, f, indent=2)
    print(f"[Setup] Created host manifest: {host_manifest_path}")

    # 7. Register in Windows Registry (HKCU)
    reg_key_path = r"Software\Google\Chrome\NativeMessagingHosts\com.prospectlens.launcher"
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_key_path)
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(host_manifest_path))
        winreg.CloseKey(key)
        print(f"[Setup] Successfully registered Native Messaging Host in Windows Registry!")
    except Exception as e:
        print(f"[Setup] Failed to write registry key: {e}")

if __name__ == "__main__":
    setup_native_messaging()
