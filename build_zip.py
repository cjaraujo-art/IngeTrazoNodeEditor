# SPDX-License-Identifier: GPL-3.0-or-later
"""
Automated packaging script for IngeTrazo Node Editor.
Packages the plugin directory into node_editor.zip with proper 'node_editor/' prefix
and calculates the SHA256 checksum for extension catalogs.
"""

import hashlib
from pathlib import Path
import zipfile

ROOT_DIR = Path(__file__).resolve().parent
ZIP_PATH = ROOT_DIR / "node_editor.zip"

INCLUDE_EXTENSIONS = {".py", ".json", ".png"}
EXCLUDE_DIRS = {"__pycache__", ".git", "tests", ".pytest_cache", ".vscode", ".idea"}
EXCLUDE_FILES = {"node_editor.zip", "build_zip.py", "apply_i18n.py", "icons_sheet.jpg", "icons_sheet.png", "new_icons.jpg", "node_editor.png"}


def build():
    print(f"[build_zip] Building {ZIP_PATH.name}...")
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for file_path in ROOT_DIR.rglob("*"):
            if file_path.is_dir():
                continue
            # Check exclusions
            parts = set(file_path.relative_to(ROOT_DIR).parts)
            if any(ex in parts for ex in EXCLUDE_DIRS):
                continue
            if file_path.name in EXCLUDE_FILES or file_path.name.startswith("."):
                continue
            if file_path.suffix.lower() not in INCLUDE_EXTENSIONS:
                continue

            rel_path = file_path.relative_to(ROOT_DIR)
            arcname = f"node_editor/{rel_path.as_posix()}"
            z.write(file_path, arcname)

    # Compute SHA256
    hasher = hashlib.sha256()
    with open(ZIP_PATH, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    sha256_hash = hasher.hexdigest()

    print(f"[build_zip] Successfully packaged {ZIP_PATH.name} ({ZIP_PATH.stat().st_size:,} bytes)")
    print(f"[build_zip] SHA256: {sha256_hash}")
    return sha256_hash


if __name__ == "__main__":
    build()
