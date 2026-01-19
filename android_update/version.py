"""Version management for auto-updates."""

import json
import os
from pathlib import Path
from typing import Any


class VersionManager:
    """Manages version information for the application."""

    def __init__(self, version_file: str = "version.json"):
        self.version_file = Path(version_file)
        self._version_data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load version data from JSON file."""
        if self.version_file.exists():
            with open(self.version_file, "r") as f:
                self._version_data = json.load(f)
        else:
            self._version_data = {
                "version": "0.0.0",
                "build": 0,
                "release_date": "",
                "update_url": "",
                "changelog": [],
            }

    def _save(self) -> None:
        """Save version data to JSON file."""
        with open(self.version_file, "w") as f:
            json.dump(self._version_data, f, indent=2)

    @property
    def version(self) -> str:
        """Get current version string."""
        return self._version_data.get("version", "0.0.0")

    @property
    def build(self) -> int:
        """Get current build number."""
        return self._version_data.get("build", 0)

    @property
    def release_date(self) -> str:
        """Get release date."""
        return self._version_data.get("release_date", "")

    @property
    def update_url(self) -> str:
        """Get update check URL."""
        return self._version_data.get("update_url", "")

    @property
    def changelog(self) -> list[str]:
        """Get changelog entries."""
        return self._version_data.get("changelog", [])

    def update_version(
        self,
        version: str | None = None,
        build: int | None = None,
        release_date: str | None = None,
        changelog: list[str] | None = None,
    ) -> None:
        """Update version information."""
        if version is not None:
            self._version_data["version"] = version
        if build is not None:
            self._version_data["build"] = build
        if release_date is not None:
            self._version_data["release_date"] = release_date
        if changelog is not None:
            self._version_data["changelog"] = changelog
        self._save()

    def compare_versions(self, other_version: str) -> int:
        """
        Compare current version with another version.

        Returns:
            -1 if current < other
            0 if current == other
            1 if current > other
        """
        current_parts = [int(x) for x in self.version.split(".")]
        other_parts = [int(x) for x in other_version.split(".")]

        for i in range(max(len(current_parts), len(other_parts))):
            current = current_parts[i] if i < len(current_parts) else 0
            other = other_parts[i] if i < len(other_parts) else 0

            if current < other:
                return -1
            elif current > other:
                return 1

        return 0

    def needs_update(self, remote_version: str) -> bool:
        """Check if remote version is newer than current."""
        return self.compare_versions(remote_version) < 0
