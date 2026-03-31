/**
 * Audio Manager — central sound system for the spaceship sim GUI.
 * Manages a single AudioContext (lazy-init on first user interaction),
 * per-category volume control, and event-driven sound triggering.
 *
 * All sounds are procedurally generated via Web Audio API oscillators,
 * noise buffers, and gain envelopes — no external audio files.
 */

import { stateManager } from "./state-manager.js";
import {
  playRailgunFire, playPDCBurst, playTorpedoLaunch, playMissileLaunch,
  playHullHit, playDetonation,
  playLockAcquired, playLockLost, playMissileWarningBeep,
  createReactorHum, createDriveBurn,
} from "./sound-generators.js";

const STORAGE_KEY = "flaxos_audio_settings";

class AudioManager {
  constructor() {
    /** @type {AudioContext|null} */
    this._ctx = null;

    // Gain nodes (created when AudioContext initializes)
    this._masterGain = null;
    this._categoryGains = {}; // weapons, engine, alerts, ambient

    // Ambient sound handles
    this._reactorHum = null;
    this._driveBurn = null;

    // Missile warning interval handle
    this._missileWarningInterval = null;
    this._incomingThreats = false;

    // State tracking for change detection
    this._prevLockState = null;
    this._prevAmmo = null; // { railgun, torpedo, missile }
    this._prevPdcEngaged = false;
    this._prevSubsystemHealth = null; // { name: health_percent }

    // Settings (loaded from localStorage)
    this._settings = {
      muted: false,
      masterVolume: 0.6,
      weapons: 0.7,
      engine: 0.5,
      alerts: 0.8,
      ambient: 0.4,
    };

    this._initialized = false;
    this._contextReady = false;
  }

  /**
   * Initialize the audio manager: load settings, attach user-interaction
   * listener for AudioContext creation, and subscribe to state updates.
   */
  init() {
    if (this._initialized) return;
    this._initialized = true;

    this._loadSettings();

    // AudioContext requires a user gesture to start (autoplay policy).
    // Listen for the first click/keydown and create the context then.
    const initAudio = () => {
      if (!this._contextReady) {
        this._createAudioContext();
      }
      document.removeEventListener("click", initAudio);
      document.removeEventListener("keydown", initAudio);
    };
    document.addEventListener("click", initAudio, { once: false });
    document.addEventListener("keydown", initAudio, { once: false });

    // Subscribe to state updates for continuous sound triggers
    stateManager.subscribe("*", (state, _key, fullState) => {
      this._onStateUpdate(fullState);
    });

    // Listen for hull damage events from the damage state manager
    document.addEventListener("subsystem-damage-update", (e) => {
      this._onDamageUpdate(e.detail);
    });
  }

  // ----------------------------------------------------------------
  // AudioContext lifecycle
  // ----------------------------------------------------------------

  _createAudioContext() {
    if (this._ctx) return;
    try {
      this._ctx = new (window.AudioContext || window.webkitAudioContext)();
    } catch (err) {
      console.warn("AudioManager: Web Audio API not available", err);
      return;
    }

    // Build gain chain: source -> category gain -> master gain -> destination
    this._masterGain = this._ctx.createGain();
    this._masterGain.connect(this._ctx.destination);

    const categories = ["weapons", "engine", "alerts", "ambient"];
    for (const cat of categories) {
      const g = this._ctx.createGain();
      g.connect(this._masterGain);
      this._categoryGains[cat] = g;
    }

    this._applySettings();
    this._startAmbient();
    this._contextReady = true;
  }

  // ----------------------------------------------------------------
  // Settings persistence
  // ----------------------------------------------------------------

  _loadSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw);
        Object.assign(this._settings, saved);
      }
    } catch (_) { /* ignore corrupt data */ }
  }

  _saveSettings() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this._settings));
    } catch (_) { /* quota exceeded or private mode */ }
  }

  _applySettings() {
    if (!this._masterGain) return;
    const s = this._settings;
    const master = s.muted ? 0 : s.masterVolume;
    this._masterGain.gain.setTargetAtTime(master, this._ctx.currentTime, 0.02);
    for (const cat of ["weapons", "engine", "alerts", "ambient"]) {
      const g = this._categoryGains[cat];
      if (g) g.gain.setTargetAtTime(s[cat] ?? 0.5, this._ctx.currentTime, 0.02);
    }
  }

  // ----------------------------------------------------------------
  // Public API for GUI controls
  // ----------------------------------------------------------------

  get muted() { return this._settings.muted; }
  get masterVolume() { return this._settings.masterVolume; }

  setMasterVolume(v) {
    this._settings.masterVolume = Math.max(0, Math.min(1, v));
    this._applySettings();
    this._saveSettings();
  }

  toggleMute() {
    this._settings.muted = !this._settings.muted;
    this._applySettings();
    this._saveSettings();
    return this._settings.muted;
  }

  setCategoryVolume(category, v) {
    if (this._settings[category] !== undefined) {
      this._settings[category] = Math.max(0, Math.min(1, v));
      this._applySettings();
      this._saveSettings();
    }
  }

  // ----------------------------------------------------------------
  // Ambient sounds
  // ----------------------------------------------------------------

  _startAmbient() {
    if (!this._ctx) return;
    const ambDest = this._categoryGains.ambient;

    this._reactorHum = createReactorHum(this._ctx, ambDest);
    this._reactorHum.start();
    this._reactorHum.setVolume(0.05); // quiet baseline

    this._driveBurn = createDriveBurn(this._ctx, this._categoryGains.engine);
    this._driveBurn.start();
    this._driveBurn.setThrottle(0);
  }

  // ----------------------------------------------------------------
  // State-driven sound triggers
  // ----------------------------------------------------------------

  _onStateUpdate(fullState) {
    if (!this._ctx || !this._contextReady) return;

    const ship = stateManager.getShipState();
    if (!ship) return;

    // -- Drive burn scales with throttle --
    const nav = stateManager.getNavigation();
    if (this._driveBurn && nav) {
      this._driveBurn.setThrottle(nav.thrust || 0);
    }

    // -- Reactor hum scales with reactor load (very subtle) --
    if (this._reactorHum) {
      const power = stateManager.getPower();
      const load = power?.reactor_load ?? power?.load ?? 0.3;
      // Scale: 0.03 at idle, 0.08 at full load
      this._reactorHum.setVolume(0.03 + load * 0.05);
    }

    // -- Weapon fire detection: ammo decrease = weapon fired --
    this._detectWeaponFire(ship);

    // -- Lock state changes --
    this._detectLockChanges(ship);

    // -- Incoming missile/torpedo warning --
    this._detectIncomingThreats();
  }

  /**
   * Detect weapon fire by comparing current ammo counts to previous tick.
   * A decrease in ammo means the weapon was fired.
   */
  _detectWeaponFire(ship) {
    const weapons = stateManager.getWeapons();
    if (!weapons) return;

    // Build current ammo snapshot
    const currentAmmo = {
      railgun: 0,
      torpedo: 0,
      missile: 0,
    };

    // Railgun ammo from truth_weapons
    const truthWeapons = weapons.truth_weapons || [];
    for (const w of truthWeapons) {
      if (w.type === "railgun" || w.weapon_type === "railgun") {
        currentAmmo.railgun += (w.ammo ?? w.rounds_remaining ?? 0);
      }
    }

    // Torpedo/missile counts
    const torpedoes = weapons.torpedoes || {};
    currentAmmo.torpedo = torpedoes.torpedo_count ?? torpedoes.torpedoes ?? 0;
    currentAmmo.missile = torpedoes.missile_count ?? torpedoes.missiles ?? 0;

    if (this._prevAmmo) {
      const dest = this._categoryGains.weapons;
      if (dest) {
        if (currentAmmo.railgun < this._prevAmmo.railgun) {
          playRailgunFire(this._ctx, dest);
        }
        if (currentAmmo.torpedo < this._prevAmmo.torpedo) {
          playTorpedoLaunch(this._ctx, dest);
        }
        if (currentAmmo.missile < this._prevAmmo.missile) {
          playMissileLaunch(this._ctx, dest);
        }
      }
    }
    this._prevAmmo = currentAmmo;

    // PDC engagement: check pdc_mode or pdc_engaged
    const pdcEngaged = !!(weapons.pdc_mode && weapons.pdc_mode !== "hold_fire");
    if (pdcEngaged && !this._prevPdcEngaged) {
      const dest = this._categoryGains.weapons;
      if (dest) playPDCBurst(this._ctx, dest);
    }
    this._prevPdcEngaged = pdcEngaged;
  }

  /**
   * Detect targeting lock state transitions and play appropriate tones.
   */
  _detectLockChanges(ship) {
    const targeting = stateManager.getTargeting();
    const lockState = targeting?.lock_state || targeting?.status || null;

    if (this._prevLockState !== null && lockState !== this._prevLockState) {
      const dest = this._categoryGains.alerts;
      if (dest) {
        if (lockState === "LOCKED" || lockState === "locked") {
          playLockAcquired(this._ctx, dest);
        } else if (
          this._prevLockState === "LOCKED" || this._prevLockState === "locked"
        ) {
          // Went from locked to something else = lock lost
          playLockLost(this._ctx, dest);
        }
      }
    }
    this._prevLockState = lockState;
  }

  /**
   * Detect incoming torpedoes/missiles targeting the player ship.
   * While threats are inbound, play a repeating warning beep.
   */
  _detectIncomingThreats() {
    const torpedoes = stateManager.getTorpedoes();
    const playerId = stateManager.getPlayerShipId();

    let hasIncoming = false;
    if (Array.isArray(torpedoes) && playerId) {
      hasIncoming = torpedoes.some(
        (t) => t.target === playerId || t.target_id === playerId
      );
    }

    if (hasIncoming && !this._incomingThreats) {
      // Start warning beep loop
      this._incomingThreats = true;
      this._missileWarningInterval = setInterval(() => {
        if (!this._ctx || !this._contextReady) return;
        const dest = this._categoryGains.alerts;
        if (dest) playMissileWarningBeep(this._ctx, dest);
      }, 200); // 50ms on + 150ms off pattern
    } else if (!hasIncoming && this._incomingThreats) {
      // Stop warning beep
      this._incomingThreats = false;
      if (this._missileWarningInterval) {
        clearInterval(this._missileWarningInterval);
        this._missileWarningInterval = null;
      }
    }
  }

  /**
   * Handle subsystem damage events from the damage state manager.
   * Compare current health percentages to previous tick; any drop = hull hit.
   */
  _onDamageUpdate(detail) {
    if (!this._ctx || !this._contextReady) return;
    if (!detail || !detail.subsystems) return;

    const dest = this._categoryGains.alerts;
    if (!dest) return;

    const subsystems = detail.subsystems;
    let hasHealthDrop = false;

    if (this._prevSubsystemHealth) {
      for (const [name, report] of Object.entries(subsystems)) {
        const pct = report.health_percent ?? 100;
        const prevPct = this._prevSubsystemHealth[name] ?? 100;
        if (pct < prevPct) {
          hasHealthDrop = true;
          break;
        }
      }
    }

    // Store current snapshot for next comparison
    const snapshot = {};
    for (const [name, report] of Object.entries(subsystems)) {
      snapshot[name] = report.health_percent ?? 100;
    }
    this._prevSubsystemHealth = snapshot;

    if (hasHealthDrop) {
      playHullHit(this._ctx, dest);
    }
  }

  /**
   * Clean up all audio resources.
   */
  destroy() {
    if (this._reactorHum) this._reactorHum.stop();
    if (this._driveBurn) this._driveBurn.stop();
    if (this._missileWarningInterval) {
      clearInterval(this._missileWarningInterval);
    }
    if (this._ctx) {
      this._ctx.close().catch(() => {});
    }
  }
}

const audioManager = new AudioManager();
export { audioManager };
