/**
 * Weapons Hardpoints Display — top-down ship schematic with live weapon states.
 *
 * Shows each weapon mount on a corvette silhouette with live state indicators:
 *   READY (green) · CHARGING (amber fill arc) · RELOADING (blue arc)
 *   EXHAUSTED (gray) · OFFLINE (red)
 * Briefly flashes white when a weapon fires (ammo decrement detected).
 *
 * Data: stateManager.getWeapons()/getCombat()
 *   .truth_weapons — per-mount state for railguns and PDCs
 *   .torpedoes     — aggregate tube state {tubes, loaded, capacity, cooldown}
 *   .missiles      — aggregate launcher state {launchers, loaded, capacity, cooldown}
 *
 * Ship nose → RIGHT (+X). SVG viewBox 0 0 320 160.
 */
import { stateManager } from "../js/state-manager.js";

// Known hardpoint positions on the ship silhouette (nose → right)
const HP_LAYOUT = {
  railgun_1: { x: 262, y: 80,  r: 13, label: "RG" },
  railgun_2: { x: 250, y: 67,  r: 12, label: "RG2" },
  pdc_1:     { x: 230, y: 57,  r: 10, label: "PDC" },
  pdc_2:     { x: 230, y: 103, r: 10, label: "PDC" },
  pdc_3:     { x: 175, y: 50,  r: 10, label: "PDC" },
  pdc_4:     { x: 175, y: 110, r: 10, label: "PDC" },
};

// Auto-position fallback for unknown mounts (placed aft of midship)
const AUTO_FALLBACK = [
  { x: 130, y: 58 }, { x: 130, y: 102 },
  { x: 105, y: 62 }, { x: 105, y: 98 },
];

// Torpedo/missile tube bank anchor positions (aft section)
const TORP_ANCHOR  = { x: 90, y: 68 };
const MSL_ANCHOR   = { x: 90, y: 92 };

const COLORS = {
  ready:     "#00cc66",
  charging:  "#ff9900",
  reloading: "#4488ff",
  exhausted: "#444",
  destroyed: "#cc2244",
  fire_flash:"#ffffff",
};

function svgArcPath(cx, cy, r, startDeg, endDeg) {
  const rad = (d) => (d - 90) * Math.PI / 180;
  const x1 = cx + r * Math.cos(rad(startDeg));
  const y1 = cy + r * Math.sin(rad(startDeg));
  const x2 = cx + r * Math.cos(rad(endDeg));
  const y2 = cy + r * Math.sin(rad(endDeg));
  const large = (endDeg - startDeg) > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
}

class WeaponsHardpointsDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._lastUpdate = 0;
    this._rafId = null;
    this._prevAmmo = {};   // mount_id → last known ammo count
    this._flashUntil = {}; // mount_id → timestamp to stop flashing
    this._knownMounts = [];
  }

  connectedCallback() {
    this._render();
    this._unsub = stateManager.subscribe("*", () => this._scheduleUpdate());
    this._scheduleUpdate();
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; }
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }
  }

  _scheduleUpdate() {
    const now = performance.now();
    if (now - this._lastUpdate < 150) return; // ~6 Hz
    this._lastUpdate = now;
    if (this._rafId) cancelAnimationFrame(this._rafId);
    this._rafId = requestAnimationFrame(() => this._update());
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; font-family: var(--font-mono, monospace); }
        svg { width: 100%; height: auto; display: block; }
        .hull { fill: #1a1a2e; stroke: #3a3a5a; stroke-width: 1.5; }
        .centerline { stroke: #2a2a4a; stroke-width: 0.5; stroke-dasharray: 4 3; }
        .hp-bg { fill: #111; stroke: #333; stroke-width: 1; }
        .hp-fill { transition: fill 0.1s; }
        .hp-ring { fill: none; stroke-width: 2.5; stroke-linecap: round; }
        .hp-label { font-size: 7px; fill: #999; text-anchor: middle; dominant-baseline: middle; pointer-events: none; }
        .hp-ammo { font-size: 6px; fill: #666; text-anchor: middle; }
        .hp-disabled { stroke: ${COLORS.destroyed}; stroke-width: 1.6; stroke-linecap: round; }
        .tube-dot { transition: fill 0.15s; }
        .tube-label { font-size: 6px; fill: #666; }
        .legend { font-size: 6px; fill: #555; }
      </style>
      <svg viewBox="0 0 320 160" xmlns="http://www.w3.org/2000/svg">
        <!-- Ship silhouette (nose pointing right) -->
        <polygon class="hull"
          points="55,80 80,50 230,52 282,80 230,108 80,110" />
        <!-- Centerline -->
        <line class="centerline" x1="55" y1="80" x2="282" y2="80" />
        <!-- Engine bells (stern) -->
        <ellipse cx="62" cy="68" rx="6" ry="4" fill="none" stroke="#2a3a5a" stroke-width="1"/>
        <ellipse cx="62" cy="92" rx="6" ry="4" fill="none" stroke="#2a3a5a" stroke-width="1"/>

        <!-- Hardpoint groups (populated by _buildHardpoints) -->
        <g id="hp-layer"></g>

        <!-- Torpedo tube bank -->
        <g id="torp-bank"></g>
        <!-- Missile launcher bank -->
        <g id="msl-bank"></g>

        <!-- Legend -->
        <g transform="translate(6,150)">
          <circle cx="4"  cy="3" r="3" fill="${COLORS.ready}"/>
          <text class="legend" x="10" y="5">READY</text>
          <circle cx="46" cy="3" r="3" fill="${COLORS.charging}"/>
          <text class="legend" x="52" y="5">CHARGING</text>
          <circle cx="96" cy="3" r="3" fill="${COLORS.reloading}"/>
          <text class="legend" x="102" y="5">RELOAD</text>
          <circle cx="138" cy="3" r="3" fill="${COLORS.exhausted}"/>
          <text class="legend" x="144" y="5">EMPTY</text>
          <circle cx="178" cy="3" r="3" fill="${COLORS.destroyed}"/>
          <text class="legend" x="184" y="5">OFFLINE</text>
        </g>
      </svg>`;
  }

  _weaponState(w) {
    if (w?.enabled === false) return "destroyed";
    if (w?.reloading) return "reloading";
    if (w?.charge_state === "charging") return "charging";
    if ((w?.ammo ?? 0) === 0) return "exhausted";
    return "ready";
  }

  _progress(w) {
    if (w.charge_state === "charging") return w.charge_progress || 0;
    if (w.reloading) return w.reload_progress || 0;
    return 0;
  }

  _buildHardpoints(mounts) {
    const layer = this.shadowRoot.getElementById("hp-layer");
    if (!layer) return;

    const mountIds = Object.keys(mounts);
    const existingIds = new Set([...layer.querySelectorAll("[data-mount]")].map(el => el.dataset.mount));
    const newIds = new Set(mountIds);

    // Remove stale groups
    existingIds.forEach(id => {
      if (!newIds.has(id)) layer.querySelector(`[data-mount="${id}"]`)?.remove();
    });

    let fallbackIdx = 0;
    mountIds.forEach(mid => {
      if (existingIds.has(mid)) return; // already present
      const pos = HP_LAYOUT[mid] || { ...AUTO_FALLBACK[fallbackIdx++ % AUTO_FALLBACK.length], r: 10, label: mid.toUpperCase().slice(0,3) };
      const { x, y, r = 10, label } = pos;
      const circ = 2 * Math.PI * (r - 1);

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("data-mount", mid);
      g.innerHTML = `
        <circle class="hp-bg"  cx="${x}" cy="${y}" r="${r}" />
        <circle class="hp-fill" data-role="fill"  cx="${x}" cy="${y}" r="${r - 3}" fill="${COLORS.ready}" />
        <path   class="hp-ring" data-role="ring"
          d="" stroke="${COLORS.ready}" />
        <g data-role="disabled-mark" visibility="hidden">
          <line class="hp-disabled" x1="${x - (r - 3)}" y1="${y - (r - 3)}" x2="${x + (r - 3)}" y2="${y + (r - 3)}" />
          <line class="hp-disabled" x1="${x + (r - 3)}" y1="${y - (r - 3)}" x2="${x - (r - 3)}" y2="${y + (r - 3)}" />
        </g>
        <text   class="hp-label" x="${x}" y="${y}">${label}</text>
        <text   class="hp-ammo" data-role="ammo" x="${x}" y="${y + r + 6}"></text>`;
      layer.appendChild(g);
    });
    this._knownMounts = mountIds;
  }

  _updateHardpoint(mid, w) {
    const g = this.shadowRoot.querySelector(`[data-mount="${mid}"]`);
    if (!g) return;

    const pos = HP_LAYOUT[mid] || AUTO_FALLBACK[0];
    const { x, y, r = 10 } = pos;

    const now = performance.now();
    const flashing = this._flashUntil[mid] && now < this._flashUntil[mid];

    // Detect fire event
    const prevAmmo = this._prevAmmo[mid];
    if (prevAmmo !== undefined && w.ammo !== null && w.ammo < prevAmmo) {
      this._flashUntil[mid] = now + 150;
    }
    this._prevAmmo[mid] = w.ammo;

    const state = this._weaponState(w);
    const prog  = this._progress(w);
    const col   = flashing ? COLORS.fire_flash : COLORS[state];

    const fillEl = g.querySelector("[data-role='fill']");
    const ringEl = g.querySelector("[data-role='ring']");
    const ammoEl = g.querySelector("[data-role='ammo']");
    const disabledEl = g.querySelector("[data-role='disabled-mark']");

    if (fillEl) fillEl.setAttribute("fill", col);
    if (disabledEl) {
      disabledEl.setAttribute("visibility", w?.enabled === false ? "visible" : "hidden");
    }

    // Progress arc (charge or reload)
    if (ringEl) {
      if (prog > 0) {
        const endDeg = prog * 360;
        ringEl.setAttribute("d", svgArcPath(x, y, r - 1, 0, endDeg));
        ringEl.setAttribute("stroke", col);
      } else {
        ringEl.setAttribute("d", "");
      }
    }

    // Ammo readout
    if (ammoEl) {
      if (w.charge_state === "charging") {
        ammoEl.textContent = `${Math.round((w.charge_progress || 0) * 100)}%`;
        ammoEl.setAttribute("fill", COLORS.charging);
      } else if (w.reloading) {
        const remaining = Math.max(0, (w.reload_time || 0) * (1 - (w.reload_progress || 0)));
        ammoEl.textContent = `${remaining.toFixed(1)}s`;
        ammoEl.setAttribute("fill", COLORS.reloading);
      } else if (w.ammo !== null && w.ammo !== undefined) {
        const pct = w.ammo_capacity > 0 ? Math.round(w.ammo / w.ammo_capacity * 100) : 100;
        ammoEl.textContent = w.ammo_capacity > 100 ? `${pct}%` : `×${w.ammo}`;
        ammoEl.setAttribute("fill", w.ammo <= 3 ? "#ff4444" : "#666");
      } else {
        ammoEl.textContent = "";
      }
    }
  }

  _updateTubeBank(anchor, count, loaded, cooldown, label, bankId) {
    const bank = this.shadowRoot.getElementById(bankId);
    if (!bank) return;
    if (count === 0) { bank.innerHTML = ""; return; }

    const { x, y } = anchor;
    const dots = Math.min(count, 6);
    const spacing = 9;
    const dotY = y;
    let html = `<text class="tube-label" x="${x - 2}" y="${dotY - 8}">${label}</text>`;

    for (let i = 0; i < dots; i++) {
      const dx = x + i * spacing;
      const full = i < loaded;
      const col = cooldown > 0 && full ? COLORS.reloading : full ? COLORS.ready : COLORS.exhausted;
      html += `<circle class="tube-dot" cx="${dx}" cy="${dotY}" r="3.5" fill="${col}" />`;
    }
    if (count > 6) {
      html += `<text class="tube-label" x="${x + dots * spacing + 2}" y="${dotY + 3}">+${count - 6}</text>`;
    }
    bank.innerHTML = html;
  }

  _update() {
    const ship = stateManager.getShipState?.();
    const weapons = stateManager.getWeapons?.() || ship?.weapons || {};
    const combat = stateManager.getCombat?.() || null;
    const truthWeapons = weapons.truth_weapons || combat?.truth_weapons || {};
    const torpedoes = weapons.torpedoes || combat?.torpedoes;
    const missiles = weapons.missiles || combat?.missiles;

    if (!Object.keys(truthWeapons).length && !torpedoes && !missiles) return;

    this._buildHardpoints(truthWeapons);

    Object.entries(truthWeapons).forEach(([mid, w]) => {
      this._updateHardpoint(mid, w);
    });

    if (torpedoes) {
      this._updateTubeBank(
        TORP_ANCHOR, torpedoes.tubes || 0, torpedoes.loaded || 0,
        torpedoes.cooldown || 0, "TORP", "torp-bank"
      );
    }
    if (missiles) {
      this._updateTubeBank(
        MSL_ANCHOR, missiles.launchers || 0, missiles.loaded || 0,
        missiles.cooldown || 0, "MSL", "msl-bank"
      );
    }

    // If flash timers are running, reschedule soon to clear them
    const now = performance.now();
    const hasFlash = Object.values(this._flashUntil).some(t => t > now);
    if (hasFlash) {
      this._lastUpdate = 0; // bypass throttle for flash clearance
      setTimeout(() => this._scheduleUpdate(), 160);
    }
  }
}

customElements.define("weapons-hardpoints-display", WeaponsHardpointsDisplay);
