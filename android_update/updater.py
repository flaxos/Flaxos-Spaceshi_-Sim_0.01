"""Auto-updater for Android/Pydroid deployment."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from .version import VersionManager


class UpdateChecker:
    """Checks for available updates from GitHub releases."""

    def __init__(self, version_manager: VersionManager):
        self.version_manager = version_manager

    def check_for_updates(self) -> dict[str, Any] | None:
        """
        Check if updates are available.

        Returns:
            Update info dict if available, None if no update or error.
        """
        update_url = self.version_manager.update_url
        if not update_url:
            return None

        try:
            with urlopen(update_url, timeout=10) as response:
                data = json.loads(response.read().decode())

            remote_version = data.get("tag_name", "").lstrip("v")
            if not remote_version:
                return None

            if self.version_manager.needs_update(remote_version):
                return {
                    "version": remote_version,
                    "name": data.get("name", ""),
                    "published_at": data.get("published_at", ""),
                    "body": data.get("body", ""),
                    "assets": data.get("assets", []),
                    "zipball_url": data.get("zipball_url", ""),
                }

            return None
        except (URLError, json.JSONDecodeError, KeyError) as e:
            print(f"Update check failed: {e}")
            return None

    def get_download_url(self, update_info: dict[str, Any]) -> str | None:
        """
        Get the best download URL from update info.

        Priority:
        1. Android APK asset
        2. Pydroid ZIP asset
        3. Source zipball
        """
        assets = update_info.get("assets", [])

        # Look for APK first
        for asset in assets:
            if asset.get("name", "").endswith(".apk"):
                return asset.get("browser_download_url")

        # Look for Pydroid ZIP
        for asset in assets:
            name = asset.get("name", "").lower()
            if "pydroid" in name and name.endswith(".zip"):
                return asset.get("browser_download_url")

        # Fall back to source zipball
        return update_info.get("zipball_url")


class AutoUpdater:
    """Handles downloading and applying updates."""

    def __init__(self, version_manager: VersionManager, app_root: str = "."):
        self.version_manager = version_manager
        self.app_root = Path(app_root).resolve()
        self.update_checker = UpdateChecker(version_manager)

    def download_update(self, url: str, dest_path: Path) -> bool:
        """
        Download update file from URL.

        Returns:
            True if download successful, False otherwise.
        """
        try:
            print(f"Downloading update from {url}...")
            with urlopen(url, timeout=30) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192

                with open(dest_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"Progress: {progress:.1f}%", end="\r")

                print("\nDownload complete!")
                return True
        except (URLError, OSError) as e:
            print(f"Download failed: {e}")
            return False

    def verify_checksum(self, file_path: Path, expected_sha256: str | None) -> bool:
        """
        Verify file checksum if expected hash is provided.

        Returns:
            True if checksum matches or no expected hash, False if mismatch.
        """
        if not expected_sha256:
            return True

        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        actual_hash = sha256_hash.hexdigest()
        return actual_hash.lower() == expected_sha256.lower()

    def extract_update(self, zip_path: Path, extract_to: Path) -> bool:
        """
        Extract update ZIP file.

        Returns:
            True if extraction successful, False otherwise.
        """
        try:
            print(f"Extracting update to {extract_to}...")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Get the root folder name (GitHub zips have a single root folder)
                namelist = zip_ref.namelist()
                if namelist:
                    root_folder = namelist[0].split("/")[0]
                else:
                    return False

                # Extract all files
                zip_ref.extractall(extract_to)

                # Move files from root folder to extract_to
                src_folder = extract_to / root_folder
                if src_folder.exists() and src_folder.is_dir():
                    for item in src_folder.iterdir():
                        dest_item = extract_to / item.name
                        if dest_item.exists():
                            if dest_item.is_dir():
                                shutil.rmtree(dest_item)
                            else:
                                dest_item.unlink()
                        shutil.move(str(item), str(extract_to))
                    src_folder.rmdir()

            print("Extraction complete!")
            return True
        except (zipfile.BadZipFile, OSError) as e:
            print(f"Extraction failed: {e}")
            return False

    def apply_update(self, source_dir: Path) -> bool:
        """
        Apply extracted update to app directory.

        Returns:
            True if update applied successfully, False otherwise.
        """
        try:
            print("Applying update...")

            # Backup critical files
            backup_files = ["version.json", "config/settings.json"]
            backups = {}

            for file_rel in backup_files:
                file_path = self.app_root / file_rel
                if file_path.exists():
                    backups[file_rel] = file_path.read_bytes()

            # Copy new files (excluding .git and other metadata)
            exclude_patterns = {".git", ".github", "__pycache__", "*.pyc", ".DS_Store"}

            for item in source_dir.rglob("*"):
                if item.is_file():
                    # Check if should be excluded
                    should_exclude = False
                    for pattern in exclude_patterns:
                        if pattern.startswith("*."):
                            if item.name.endswith(pattern[1:]):
                                should_exclude = True
                                break
                        elif pattern in item.parts:
                            should_exclude = True
                            break

                    if should_exclude:
                        continue

                    # Calculate relative path
                    rel_path = item.relative_to(source_dir)
                    dest_path = self.app_root / rel_path

                    # Create parent directories
                    dest_path.parent.mkdir(parents=True, exist_ok=True)

                    # Copy file
                    shutil.copy2(item, dest_path)

            # Restore backups
            for file_rel, content in backups.items():
                file_path = self.app_root / file_rel
                file_path.write_bytes(content)

            print("Update applied successfully!")
            return True
        except OSError as e:
            print(f"Update application failed: {e}")
            return False

    def perform_update(self) -> bool:
        """
        Check for and apply updates if available.

        Returns:
            True if update was applied, False otherwise.
        """
        print("Checking for updates...")
        update_info = self.update_checker.check_for_updates()

        if not update_info:
            print("No updates available.")
            return False

        print(f"Update available: v{update_info['version']}")
        print(f"Release: {update_info['name']}")
        print(f"\nChangelog:\n{update_info['body']}\n")

        download_url = self.update_checker.get_download_url(update_info)
        if not download_url:
            print("No valid download URL found.")
            return False

        # Check if this is an APK update
        if download_url.endswith(".apk"):
            print("APK update detected!")
            print(
                "Please download and install manually from:"
            )
            print(download_url)
            return False

        # Download and apply source update
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "update.zip"
            extract_path = temp_path / "extracted"
            extract_path.mkdir()

            # Download
            if not self.download_update(download_url, zip_path):
                return False

            # Extract
            if not self.extract_update(zip_path, extract_path):
                return False

            # Apply
            if not self.apply_update(extract_path):
                return False

            # Update version info
            self.version_manager.update_version(
                version=update_info["version"],
                release_date=update_info["published_at"],
            )

            print(f"\nSuccessfully updated to v{update_info['version']}!")
            print("Please restart the application.")
            return True
