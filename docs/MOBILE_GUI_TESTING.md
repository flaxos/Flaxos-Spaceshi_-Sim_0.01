# Mobile GUI Testing Checklist

**Project**: Flaxos Spaceship Simulator  
**Version**: Phase 6 Mobile Optimization  
**Last Updated**: 2026-01-24

---

## Overview

This document provides a testing checklist for validating the mobile GUI on Android (Pydroid/Chrome) and iOS (Safari/Chrome) browsers.

---

## Prerequisites

### Server Setup
1. Start the simulation server:
   ```bash
   python -m server.station_server --fleet-dir hybrid_fleet --dt 0.1 --host 0.0.0.0 --port 8765
   ```

2. Start the WebSocket bridge:
   ```bash
   python gui/ws_bridge.py --host 0.0.0.0 --port 8080
   ```

3. Serve the GUI (development):
   ```bash
   python -m http.server 8000 --directory gui
   ```

4. Or use the all-in-one launcher:
   ```bash
   python tools/start_gui_stack.py --server station
   ```

### Device Requirements
- **Android**: Chrome 90+ or Pydroid3 WebView
- **iOS**: Safari 14+ or Chrome for iOS
- Both devices must be on the same network as the server

---

## Testing Checklist

### 1. Initial Load

| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Page loads without errors | [ ] | [ ] | Check console for JS errors |
| Fonts load correctly | [ ] | [ ] | JetBrains Mono, Inter |
| CSS variables applied | [ ] | [ ] | Dark theme colors visible |
| Connection bar visible | [ ] | [ ] | Shows connection status |

### 2. Responsive Detection

| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Mobile layout activates at <=768px | [ ] | [ ] | Tab bar should appear |
| Desktop layout at >768px | [ ] | [ ] | Standard grid layout |
| Rotation handles correctly | [ ] | [ ] | Portrait to landscape |
| No horizontal scroll | [ ] | [ ] | Swipe left/right within bounds |

### 3. Tab Navigation

| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Tab bar visible | [ ] | [ ] | 5 tabs: NAV, SEN, WPN, LOG, SYS |
| Tap to switch tabs | [ ] | [ ] | Visual feedback on tap |
| Active tab highlighted | [ ] | [ ] | Different background color |
| Correct panels shown per tab | [ ] | [ ] | Only relevant panels visible |
| Swipe left/right changes tabs | [ ] | [ ] | Horizontal swipe gesture |

### 4. Touch Controls

#### Touch Throttle
| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Throttle visible in control zone | [ ] | [ ] | Bottom of screen |
| Drag to change value | [ ] | [ ] | Vertical drag |
| Snaps to 10% increments | [ ] | [ ] | 0%, 10%, 20%, etc. |
| Value displayed correctly | [ ] | [ ] | Shows percentage |
| Emergency stop button works | [ ] | [ ] | Sets throttle to 0 |
| Double-tap emergency stop | [ ] | [ ] | Quick tap detection |
| Server receives commands | [ ] | [ ] | Check ship state |

#### Touch Joystick
| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Joystick visible in control zone | [ ] | [ ] | Bottom of screen |
| Drag from center | [ ] | [ ] | Smooth movement |
| Returns to center on release | [ ] | [ ] | Animated return |
| X controls yaw | [ ] | [ ] | Left/right |
| Y controls pitch | [ ] | [ ] | Up/down |
| Values displayed | [ ] | [ ] | P: and Y: labels |
| Server receives angular velocity | [ ] | [ ] | Check ship state |

#### Quick Actions
| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Fire button works | [ ] | [ ] | Sends fire_weapon |
| Lock button works | [ ] | [ ] | Sends lock_target |
| Autopilot button works | [ ] | [ ] | Sends autopilot hold |
| Ping button works | [ ] | [ ] | Sends ping_sensors |
| Visual feedback on tap | [ ] | [ ] | Button animates |

### 5. Touch Targets

| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| All buttons >= 44px | [ ] | [ ] | Measure tap targets |
| Input fields >= 44px | [ ] | [ ] | Command prompt input |
| Contact rows tappable | [ ] | [ ] | Sensor contacts list |
| Dropdown selects work | [ ] | [ ] | Autopilot target dropdown |

### 6. Panel Content

| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Ship Status displays | [ ] | [ ] | Hull, fuel, power bars |
| Navigation displays | [ ] | [ ] | Position, velocity, heading |
| Sensor contacts list | [ ] | [ ] | Contact rows visible |
| Targeting display | [ ] | [ ] | Lock status shown |
| Weapons status | [ ] | [ ] | Ammo counts visible |
| Event log scrolls | [ ] | [ ] | Touch scroll working |
| Command prompt accepts input | [ ] | [ ] | Keyboard appears |

### 7. Performance

| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Smooth scrolling | [ ] | [ ] | 60 FPS target |
| No lag on tab switch | [ ] | [ ] | < 100ms transition |
| Touch response < 100ms | [ ] | [ ] | Immediate feedback |
| State updates real-time | [ ] | [ ] | 200ms polling |
| Memory stable | [ ] | [ ] | No leaks over time |

### 8. Orientation & Safe Areas

| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Portrait mode works | [ ] | [ ] | Primary mobile orientation |
| Landscape mode works | [ ] | [ ] | Compact layout |
| iOS notch handled | [ ] | [ ] | Safe area insets |
| Android nav bar handled | [ ] | [ ] | Bottom padding |

### 9. WebSocket Connection

| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Initial connection | [ ] | [ ] | Status shows connected |
| Reconnect on disconnect | [ ] | [ ] | Auto-reconnect works |
| Commands reach server | [ ] | [ ] | Server logs show commands |
| State updates received | [ ] | [ ] | UI updates with state |

### 10. Scenario Playthrough

| Test | Android | iOS | Notes |
|------|---------|-----|-------|
| Load Tutorial scenario | [ ] | [ ] | From SYS tab |
| Navigate using touch controls | [ ] | [ ] | Throttle and joystick |
| Lock target | [ ] | [ ] | Via quick action |
| Complete scenario objective | [ ] | [ ] | Full playthrough |

---

## Known Limitations

1. **iOS Safari**: Some CSS custom properties may not update dynamically
2. **Android WebView**: Touch event timing may vary
3. **Landscape**: Reduced control zone height
4. **Slow networks**: State updates may lag

---

## Troubleshooting

### Touch Not Responding
- Check `touch-action: none` on control elements
- Verify no overlapping transparent elements
- Test with browser DevTools touch simulation

### Layout Issues
- Clear browser cache
- Check viewport meta tag
- Test with DevTools device emulation first

### Connection Issues
- Verify server is reachable (ping)
- Check WebSocket bridge is running
- Ensure correct port in URL

---

## Reporting Issues

Include:
1. Device model and OS version
2. Browser and version
3. Screenshot or screen recording
4. Console errors (if any)
5. Steps to reproduce

---

**Document Maintained By**: Development Team  
**Review Frequency**: After each mobile update
