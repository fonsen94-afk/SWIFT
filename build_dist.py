"""
build_dist.py

Helper script to build a distributable using PyInstaller and ensure the SWIFT logo file
located in ./assets (e.g., assets/swift_logo.png or assets/swift_logo.svg) is included and
available in the built distribution.

Usage:
  - Place your swift_alliance_bank.py, swift_messages.py, swift_alliance_gui.py, swift_iso_validator.py, etc. in the project root.
  - Place the SWIFT logo file (swift_logo.png or swift_logo.svg) into ./assets/ (ensure you have rights).
  - Install pyinstaller: pip install pyinstaller
  - Run: python build_dist.py

Security / legal reminder:
  - Do not include any logo you don't have rights to distribute.
"""

import os
import shutil
import subprocess
import sys

APP_NAME = "swift_alliance_gui"
ENTRY_SCRIPT = "swift_alliance_gui.py"
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILENAMES = ["swift_logo.png", "swift_logo.svg", "swift_logo.jpg"]

def find_logo():
    for fname in LOGO_FILENAMES:
        path = os.path.join(ASSETS_DIR, fname)
        if os.path.exists(path):
            return path
    return None

def build_with_pyinstaller():
    # Ensure pyinstaller is available
    try:
        import PyInstaller  # noqa: F401
    except Exception:
        print("PyInstaller not found. Install with: pip install pyinstaller")
        sys.exit(1)

    logo_path = find_logo()
    if not logo_path:
        print("Warning: No logo found in assets/. You should add swift_logo.png or swift_logo.svg to ./assets/")
    else:
        print(f"Found logo: {logo_path}")

    # Build args: one-folder build so assets are local alongside executable
    add_data = f"{ASSETS_DIR}{os.pathsep}assets"
    args = [
        "pyinstaller",
        "--noconfirm",
        "--name", APP_NAME,
        "--onedir",
        "--add-data", add_data,
        ENTRY_SCRIPT
    ]

    print("Running PyInstaller...")
    ret = subprocess.call(args)
    if ret != 0:
        print("PyInstaller failed.")
        sys.exit(ret)

    print("Build completed. Dist folder available at ./dist/{}".format(APP_NAME))

def extract_logo_to_dist():
    logo_path = find_logo()
    if not logo_path:
        print("No logo to extract; skipping extraction step.")
        return

    # expected pyinstaller dist folder
    dist_assets = os.path.join("dist", APP_NAME, "assets")
    if not os.path.exists(dist_assets):
        print("Dist assets folder not found; build may have failed or different layout used.")
        return

    # copy logo to dist root for easy access (also kept in assets)
    dst = os.path.join("dist", APP_NAME, os.path.basename(logo_path))
    try:
        shutil.copy2(logo_path, dst)
        print(f"Copied logo to: {dst}")
    except Exception as e:
        print(f"Failed to copy logo to dist: {e}")

def main():
    build_with_pyinstaller()
    extract_logo_to_dist()
    print("Build helper finished. Please verify the distribution and contained assets.")

if __name__ == "__main__":
    main()