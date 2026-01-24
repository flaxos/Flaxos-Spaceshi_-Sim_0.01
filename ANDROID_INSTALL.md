# Android/Pydroid Installation Guide

Quick setup guide for running Flaxos Spaceship Sim on Android with Pydroid3.

## Prerequisites

1. **Pydroid 3** app installed from Google Play Store
   - [Download Pydroid 3](https://play.google.com/store/apps/details?id=ru.iiec.pydroid3)

2. **Storage space**: ~50 MB for app + dependencies

3. **Python 3.8+** (included in Pydroid 3)

## Installation Steps

### Method 1: From GitHub Release (Recommended)

1. **Download Latest Release**
   - Go to: https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/releases/latest
   - Download `flaxos-spaceship-sim-pydroid-*.zip`

2. **Extract on Android**
   - Use a file manager to extract the ZIP
   - Extract to a location like `/sdcard/FlaxosSpaceshipSim/`

3. **Open in Pydroid 3**
   - Open Pydroid 3
   - Navigate to the extracted folder
   - Open `pydroid_run.py`

4. **Install Dependencies**
   ```python
   # In Pydroid terminal:
   pip install numpy pyyaml flask
   ```

5. **Run the App**
   ```python
   python pydroid_run.py
   ```

6. **Open in Browser**
   - Open your mobile browser
   - Navigate to: `http://localhost:5000`
   - You should see the Flaxos Mobile Station Console!

### Method 2: Clone from Git

1. **Install Git in Pydroid**
   ```bash
   pip install gitpython
   ```

2. **Clone Repository**
   ```bash
   git clone https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01.git
   cd Flaxos-Spaceshi_-Sim_0.01
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the App**
   ```bash
   python pydroid_run.py
   ```

5. **Open in Browser**
   - Navigate to `http://localhost:5000`

## Configuration

### Server Settings

Edit connection settings in the UI:
- **Host**: `127.0.0.1` (for local server) or your PC's IP for networked play
- **Port**: `8765` (default)

### Performance Tips

1. **Close Background Apps**: Free up RAM for better performance
2. **Use Wi-Fi**: Better for networked gameplay
3. **Adjust Delta-T**: Use larger time steps for lower-end devices
   ```bash
   python pydroid_run.py --dt 0.2  # Instead of 0.1
   ```

## Auto-Updates

The app includes built-in auto-updates!

1. **Open the Mobile UI** (`http://localhost:5000`)
2. **Navigate to "System Updates"** panel
3. **Click "Check for Updates"**
4. **Click "Apply Update"** if available
5. **Restart the app** when prompted

See [docs/ANDROID_AUTO_UPDATE.md](docs/ANDROID_AUTO_UPDATE.md) for details.

## Troubleshooting

### "Module not found" errors

**Solution**: Install missing dependencies
```bash
pip install numpy pyyaml flask
```

### "Address already in use" error

**Solution**: Stop other apps using port 5000 or change the port
```bash
python pydroid_run.py --ui-port 5001
```

### Server won't start

**Solution**: Check if the server is already running
```bash
# Kill any running instances
pkill -f pydroid_run
# Then restart
python pydroid_run.py
```

### Can't connect to server

**Solutions**:
1. Verify server is running (check Pydroid terminal)
2. Check host/port settings in UI
3. Ensure no firewall blocking (on networked play)

### UI is slow/laggy

**Solutions**:
1. Increase delta-t: `--dt 0.2`
2. Close background apps
3. Restart Pydroid
4. Clear browser cache

## Network Play

To connect mobile device to desktop server:

1. **Start server on desktop**:
   ```bash
   # Recommended: station-aware server (multi-crew / permissions)
   python -m server.station_server --host 0.0.0.0 --port 8765

   # Minimal server (no stations)
   # python -m server.run_server --host 0.0.0.0 --port 8765
   ```

2. **Find desktop IP address**:
   - Windows: `ipconfig`
   - Linux/Mac: `ifconfig` or `ip addr`
   - Look for `192.168.x.x` address

3. **Configure mobile UI**:
   - Host: `192.168.x.x` (your desktop IP)
   - Port: `8765`

4. **Ensure same network**: Both devices on same Wi-Fi

## Features Available on Android

Core features work on Android:
- ✅ Full spaceship simulation
- ✅ Navigation and autopilot
- ✅ Sensors (passive/active)
- ✅ Weapons systems
- ✅ Scenario missions
- ✅ Auto-updates
- ✅ TCP client connectivity over LAN

## Performance Benchmarks

Tested on various devices:

| Device | RAM | Performance |
|--------|-----|-------------|
| High-end (2023+) | 8GB+ | Excellent (dt=0.05) |
| Mid-range (2020+) | 4-6GB | Good (dt=0.1) |
| Budget (2018+) | 2-4GB | Playable (dt=0.2) |

## Support

- **Documentation**: See `/docs` folder
- **Issues**: https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/issues
- **Updates**: Check "System Updates" panel in UI

## What's Next?

1. **Explore the tutorial**: Try scenario `01_tutorial_intercept.yaml`
2. **Read the docs**: Check out `README.md` and `docs/`
3. **Join multiplayer**: Connect to a friend's server
4. **Customize**: Edit ship configs in `hybrid_fleet/`

Enjoy flying! 🚀
