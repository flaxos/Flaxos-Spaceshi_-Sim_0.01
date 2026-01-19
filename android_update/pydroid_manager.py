"""Pydroid-specific update manager with UI integration."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .updater import AutoUpdater
from .version import VersionManager


class PydroidUpdateManager:
    """Manages updates specifically for Pydroid environment."""

    def __init__(self, app_root: str = "."):
        self.app_root = Path(app_root).resolve()
        self.version_manager = VersionManager(self.app_root / "version.json")
        self.updater = AutoUpdater(self.version_manager, app_root)

    def get_current_version_info(self) -> dict[str, Any]:
        """Get current version information."""
        return {
            "version": self.version_manager.version,
            "build": self.version_manager.build,
            "release_date": self.version_manager.release_date,
            "changelog": self.version_manager.changelog,
        }

    def check_update_available(self) -> dict[str, Any]:
        """
        Check if update is available.

        Returns:
            Dict with 'available' (bool) and 'update_info' (dict or None)
        """
        update_info = self.updater.update_checker.check_for_updates()
        return {
            "available": update_info is not None,
            "update_info": update_info,
            "current_version": self.version_manager.version,
        }

    def download_and_apply_update(self, background: bool = False) -> dict[str, Any]:
        """
        Download and apply available update.

        Args:
            background: If True, run update in background (Pydroid may not support)

        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        try:
            success = self.updater.perform_update()
            if success:
                return {
                    "success": True,
                    "message": f"Updated to v{self.version_manager.version}. Please restart.",
                }
            else:
                return {
                    "success": False,
                    "message": "No update available or update failed.",
                }
        except Exception as e:
            return {"success": False, "message": f"Update failed: {e}"}

    def is_pydroid_environment(self) -> bool:
        """Check if running in Pydroid environment."""
        # Check for common Pydroid indicators
        pydroid_indicators = [
            "/data/user/0/ru.iiec.pydroid3",
            "PYDROID3",
            "com.termux",
        ]

        for indicator in pydroid_indicators:
            if indicator in sys.executable or indicator in os.environ.get("PATH", ""):
                return True

        return False

    def restart_application(self) -> None:
        """
        Attempt to restart the application (limited in Pydroid).

        Note: Full restart may not be possible in Pydroid.
        User should manually restart.
        """
        print("\n" + "=" * 50)
        print("UPDATE COMPLETE!")
        print("=" * 50)
        print("\nPlease RESTART the application:")
        print("1. Close Pydroid completely")
        print("2. Reopen Pydroid")
        print("3. Run: python pydroid_run.py")
        print("\n" + "=" * 50)

        if self.is_pydroid_environment():
            print("\nNote: Auto-restart not available in Pydroid")
        else:
            # Try to restart on desktop/server
            try:
                python = sys.executable
                os.execl(python, python, *sys.argv)
            except Exception as e:
                print(f"Auto-restart failed: {e}")


def create_update_api_routes(app, manager: PydroidUpdateManager):
    """
    Add update API routes to Flask app.

    Usage:
        from android_update.pydroid_manager import PydroidUpdateManager, create_update_api_routes

        manager = PydroidUpdateManager()
        create_update_api_routes(app, manager)
    """

    @app.get("/api/version")
    def api_version():
        """Get current version info."""
        from flask import jsonify

        return jsonify(manager.get_current_version_info())

    @app.get("/api/check_update")
    def api_check_update():
        """Check for available updates."""
        from flask import jsonify

        result = manager.check_update_available()
        return jsonify(result)

    @app.post("/api/apply_update")
    def api_apply_update():
        """Download and apply update."""
        from flask import jsonify

        result = manager.download_and_apply_update()
        return jsonify(result)


# CLI tool for manual updates
def main():
    """CLI tool for checking and applying updates."""
    import argparse

    parser = argparse.ArgumentParser(description="Flaxos Spaceship Sim Update Manager")
    parser.add_argument(
        "--check", action="store_true", help="Check for available updates"
    )
    parser.add_argument("--apply", action="store_true", help="Apply available updates")
    parser.add_argument(
        "--info", action="store_true", help="Show current version info"
    )
    parser.add_argument(
        "--app-root", default=".", help="Application root directory"
    )
    args = parser.parse_args()

    manager = PydroidUpdateManager(args.app_root)

    if args.info:
        info = manager.get_current_version_info()
        print(json.dumps(info, indent=2))

    elif args.check:
        result = manager.check_update_available()
        if result["available"]:
            update = result["update_info"]
            print(f"Update available: v{update['version']}")
            print(f"Current version: v{result['current_version']}")
            print(f"\nRelease: {update['name']}")
            print(f"\nChangelog:\n{update['body']}")
        else:
            print(f"No updates available (current: v{result['current_version']})")

    elif args.apply:
        print("Starting update process...")
        result = manager.download_and_apply_update()
        print(result["message"])
        if result["success"]:
            manager.restart_application()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
