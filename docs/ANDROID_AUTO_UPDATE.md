# Android Auto-Update System

Complete guide for the Flaxos Spaceship Sim Android auto-update system.

## Overview

This project includes a comprehensive auto-update system that automatically keeps the Android/Pydroid standalone version in sync with the latest releases from GitHub. The system supports:

- **Automatic update checking** from GitHub releases
- **One-click updates** via mobile UI
- **Version management** with semantic versioning
- **Pydroid3 compatibility** for Android deployment
- **APK generation** (optional) via Buildozer
- **Automated releases** via GitHub Actions

## Architecture

### Components

1. **Version Manager** (`android_update/version.py`)
   - Tracks current version, build number, and release date
   - Compares versions to determine if updates are needed
   - Stores version info in `version.json`

2. **Update Checker** (`android_update/updater.py`)
   - Polls GitHub API for latest releases
   - Prioritizes APK → Pydroid ZIP → Source zipball
   - Validates checksums (when available)

3. **Auto Updater** (`android_update/updater.py`)
   - Downloads update packages
   - Extracts and applies updates
   - Preserves critical config files during updates
   - Handles backup and rollback scenarios

4. **Pydroid Manager** (`android_update/pydroid_manager.py`)
   - Pydroid-specific update logic
   - Flask API integration
   - CLI tools for manual updates
   - Environment detection

5. **Mobile UI Integration** (`mobile_ui/`)
   - Web-based update interface
   - Real-time update status
   - Changelog display
   - One-click apply updates

6. **GitHub Actions** (`.github/workflows/android-release.yml`)
   - Automated release creation on version tags
   - Package building (Pydroid ZIP)
   - Checksum generation
   - APK building (when configured)

## Quick Start

### For End Users (Pydroid3)

1. **Install the app** (first time):
   ```bash
   # In Pydroid3:
   pip install numpy pyyaml flask
   python pydroid_run.py
   ```

2. **Check for updates**:
   - Open the mobile UI in your browser (`http://localhost:5000`)
   - Navigate to the "System Updates" panel
   - Click "Check for Updates"
   - If an update is available, click "Apply Update"
   - Restart the app when prompted

3. **Automatic checks**:
   - The UI automatically checks for updates 5 seconds after page load
   - You can manually check at any time

### For Developers

#### Creating a Release

1. **Update version.json**:
   ```bash
   # Edit version.json with new version number
   vim version.json
   ```

2. **Commit and tag**:
   ```bash
   git add version.json
   git commit -m "Bump version to v0.2.0"
   git tag v0.2.0
   git push origin claude/android-auto-update-setup-Rp3FQ
   git push origin v0.2.0
   ```

3. **GitHub Actions automatically**:
   - Builds Pydroid package
   - Generates checksums
   - Creates GitHub release
   - Uploads assets

4. **Users can now update** via the mobile UI!

#### Manual Release (Alternative)

```bash
# Trigger workflow manually
gh workflow run android-release.yml -f version=0.2.0
```

## CLI Usage

### Check Version

```bash
python -m android_update.pydroid_manager --info
```

Output:
```json
{
  "version": "0.1.0",
  "build": 1,
  "release_date": "2026-01-19",
  "changelog": [...]
}
```

### Check for Updates

```bash
python -m android_update.pydroid_manager --check
```

### Apply Updates

```bash
python -m android_update.pydroid_manager --apply
```

## API Endpoints

The mobile UI exposes the following API endpoints:

### GET `/api/version`

Get current version information.

**Response**:
```json
{
  "version": "0.1.0",
  "build": 1,
  "release_date": "2026-01-19",
  "changelog": ["Initial release", ...]
}
```

### GET `/api/check_update`

Check for available updates.

**Response**:
```json
{
  "available": true,
  "current_version": "0.1.0",
  "update_info": {
    "version": "0.2.0",
    "name": "Version 0.2.0",
    "published_at": "2026-01-20T12:00:00Z",
    "body": "Changelog text...",
    "assets": [...]
  }
}
```

### POST `/api/apply_update`

Download and apply available update.

**Response**:
```json
{
  "success": true,
  "message": "Updated to v0.2.0. Please restart."
}
```

## APK Generation (Optional)

### Prerequisites

1. Install Buildozer:
   ```bash
   pip install buildozer
   ```

2. Install Android SDK and NDK (Buildozer can do this automatically)

3. Create icon file:
   ```bash
   # Place icon at mobile_ui/static/icon.png
   # Recommended size: 512x512 PNG
   ```

### Build APK

```bash
buildozer android debug
```

The APK will be created in `bin/flaxosspaceshipsim-0.1.0-debug.apk`

### Enable APK in GitHub Actions

Edit `.github/workflows/android-release.yml`:

```yaml
build-apk:
  runs-on: ubuntu-latest
  if: true  # Change from false to true
```

## Update Flow Diagram

```
User opens Mobile UI
  ↓
[Auto-check after 5s]
  ↓
Fetch /api/check_update
  ↓
Query GitHub API
  ↓
Compare versions
  ↓
[Update Available?]
  ↓ YES
Show "Apply Update" button
  ↓
User clicks "Apply Update"
  ↓
POST /api/apply_update
  ↓
Download package from GitHub
  ↓
Extract to temp directory
  ↓
Backup critical files
  ↓
Copy new files to app directory
  ↓
Restore backups
  ↓
Update version.json
  ↓
Notify user to restart
```

## Configuration

### version.json

```json
{
  "version": "0.1.0",           // Semantic version (MAJOR.MINOR.PATCH)
  "build": 1,                    // Auto-incremented build number
  "release_date": "2026-01-19", // ISO date string
  "update_url": "https://...",  // GitHub API URL for releases
  "changelog": [                // Array of changelog entries
    "Feature 1",
    "Bug fix 2"
  ]
}
```

### Update URL Format

For public repos:
```
https://api.github.com/repos/{owner}/{repo}/releases/latest
```

For private repos (requires auth token):
```
https://{token}@api.github.com/repos/{owner}/{repo}/releases/latest
```

## Troubleshooting

### Update Check Fails

**Symptom**: "Update check failed" error

**Solutions**:
1. Check internet connectivity
2. Verify `update_url` in `version.json` is correct
3. Check GitHub API rate limits
4. Ensure repository releases exist

### Download Fails

**Symptom**: Download stalls or fails

**Solutions**:
1. Check available storage space
2. Verify stable internet connection
3. Try manual download from GitHub
4. Check file permissions

### Update Doesn't Apply

**Symptom**: Update downloads but doesn't apply

**Solutions**:
1. Check write permissions in app directory
2. Verify sufficient storage space
3. Check for file locks (close all app instances)
4. Review error logs in command log

### APK Build Fails

**Symptom**: Buildozer fails to create APK

**Solutions**:
1. Install all Buildozer dependencies
2. Ensure Android SDK/NDK are installed
3. Check `buildozer.spec` configuration
4. Review Buildozer logs: `.buildozer/android/platform/build-*/build.log`

## Best Practices

### For Developers

1. **Semantic Versioning**: Use MAJOR.MINOR.PATCH
   - MAJOR: Breaking changes
   - MINOR: New features (backward compatible)
   - PATCH: Bug fixes

2. **Test Before Release**:
   ```bash
   python -m pytest -q
   python pydroid_run.py  # Smoke test
   ```

3. **Write Clear Changelogs**: Include in release notes
   - What's new
   - What's fixed
   - What's changed
   - Breaking changes (if any)

4. **Tag Properly**:
   ```bash
   git tag -a v0.2.0 -m "Version 0.2.0: Add feature X"
   ```

### For Users

1. **Backup Before Updating**: Copy your config files
2. **Check Changelog**: Read what's changed
3. **Test After Update**: Verify core functionality
4. **Report Issues**: Use GitHub issues for problems

## Security Considerations

1. **HTTPS Only**: All downloads use HTTPS
2. **Checksum Verification**: When available, checksums are verified
3. **No Auto-Update Without User Consent**: User must click "Apply Update"
4. **Backup Critical Files**: Config preserved during updates
5. **No Root Required**: Works in user space

## Performance

- **Update Check**: ~1-2 seconds (API request)
- **Download**: Depends on connection speed (~5-10 MB package)
- **Apply**: ~5-10 seconds (extraction + file copy)
- **Total**: ~30-60 seconds for typical update

## Future Enhancements

- [ ] Delta updates (only changed files)
- [ ] Automatic rollback on failure
- [ ] Update scheduling (e.g., "Update at 2 AM")
- [ ] Differential updates (patch-based)
- [ ] Multi-source update mirrors
- [ ] Cryptographic signature verification
- [ ] In-app update progress bar
- [ ] Background update downloads

## Support

For issues or questions:

- GitHub Issues: https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/issues
- Documentation: See README.md and other docs in `/docs`

## License

Same as main project (see LICENSE file)
