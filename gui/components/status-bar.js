/**
 * Status Bar Component
 * Compact always-visible bar showing hull %, key subsystem icons, fuel gauge, ammo count.
 * Color-coded: green=nominal, yellow=impaired, red=critical.
 */

import { stateManager } from "../js/state-manager.js";

class StatusBar extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          background: var(--bg-panel, #12121a);
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          padding: 6px 12px;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.75rem;
        }

        .status-bar {
          display: flex;
          align-items: center;
          gap: 16px;
          flex-wrap: wrap;
        }

        .status-group {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .status-label {
          color: var(--text-dim, #555566);
          font-size: 0.65rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          font-weight: 600;
        }

        .status-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          font-weight: 600;
        }

        .status-value.nominal { color: var(--status-nominal, #00ff88); }
        .status-value.warning { color: var(--status-warning, #ffaa00); }
        .status-value.critical { color: var(--status-critical, #ff4444); }
        .status-value.info { color: var(--status-info, #00aaff); }

        .mini-bar {
          width: 60px;
          height: 6px;
          background: var(--bg-input, #1a1a24);
          border-radius: 3px;
          overflow: hidden;
        }

        .mini-bar-fill {
          height: 100%;
          transition: width 0.3s ease;
        }

        .mini-bar-fill.nominal { background: var(--status-nominal, #00ff88); }
        .mini-bar-fill.warning { background: var(--status-warning, #ffaa00); }
        .mini-bar-fill.critical { background: var(--status-critical, #ff4444); }

        .separator {
          width: 1px;
          height: 16px;
          background: var(--border-default, #2a2a3a);
        }

        .subsystem-icons {
          display: flex;
          gap: 6px;
        }

        .subsystem-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          position: relative;
        }

        .subsystem-dot.online {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 4px var(--status-nominal, #00ff88);
        }

        .subsystem-dot.warning {
          background: var(--status-warning, #ffaa00);
          box-shadow: 0 0 4px var(--status-warning, #ffaa00);
        }

        .subsystem-dot.offline {
          background: var(--status-offline, #555566);
        }

        .subsystem-dot.error {
          background: var(--status-critical, #ff4444);
          box-shadow: 0 0 4px var(--status-critical, #ff4444);
        }

        .subsystem-dot[title] {
          cursor: help;
        }

        .empty-state {
          color: var(--text-dim, #555566);
          font-style: italic;
          font-size: 0.75rem;
        }

        @media (max-width: 768px) {
          .status-bar {
            gap: 10px;
            justify-content: center;
          }

          .status-label {
            font-size: 0.6rem;
          }

          .mini-bar {
            width: 40px;
          }
        }

        /* Constrain height on small viewports so the bar doesn't eat screen space when it wraps */
        @media (max-height: 800px) {
          :host {
            max-height: 36px;
            overflow: hidden;
          }
        }

        /* Hide entirely on extremely small viewports (landscape phones, small embeds) */
        @media (max-height: 600px) {
          :host {
            display: none;
          }
        }

        /* Proposal notification badge — CPU-ASSIST tier only */
        .proposal-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 2px 8px;
          border-radius: 10px;
          background: rgba(192, 160, 255, 0.12);
          border: 1px solid rgba(192, 160, 255, 0.4);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          font-weight: 700;
          color: #c0a0ff;
          letter-spacing: 0.03em;
          animation: proposalBadgePulse 2s ease-in-out infinite;
        }

        .proposal-badge.hidden {
          display: none;
        }

        .badge-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #c0a0ff;
          box-shadow: 0 0 6px rgba(192, 160, 255, 0.6);
        }

        .badge-num {
          color: #e0d0ff;
        }

        @keyframes proposalBadgePulse {
          0%, 100% { box-shadow: none; }
          50% { box-shadow: 0 0 10px rgba(192, 160, 255, 0.3); }
        }

        @media (prefers-reduced-motion: reduce) {
          .proposal-badge { animation: none; }
        }
      </style>

      <div class="status-bar" id="bar">
        <span class="empty-state">Awaiting ship data...</span>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    const bar = this.shadowRoot.getElementById("bar");

    if (!ship || Object.keys(ship).length === 0) {
      bar.innerHTML = '<span class="empty-state">Awaiting ship data...</span>';
      return;
    }

    // Hull
    const hull = this._getHullPercent(ship);
    const hullClass = hull > 50 ? "nominal" : hull > 25 ? "warning" : "critical";

    // Fuel
    const fuel = this._getFuelPercent(ship);
    const fuelClass = fuel > 50 ? "nominal" : fuel > 20 ? "warning" : "critical";

    // Ammo
    const ammo = this._getAmmoSummary(ship);

    // Subsystems
    const systems = this._getSubsystems(ship);

    // Speed
    const nav = stateManager.getNavigation();
    const vel = nav.velocity || [0, 0, 0];
    const speed = Math.sqrt(vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2);

    bar.innerHTML = `
      <div class="status-group">
        <span class="status-label">HULL</span>
        <span class="status-value ${hullClass}">${hull.toFixed(0)}%</span>
        <div class="mini-bar">
          <div class="mini-bar-fill ${hullClass}" style="width: ${hull}%"></div>
        </div>
      </div>

      <div class="separator"></div>

      <div class="status-group">
        <span class="status-label">SYS</span>
        <div class="subsystem-icons">
          ${systems.map(s =>
            `<div class="subsystem-dot ${s.status}" title="${s.name}: ${s.status.toUpperCase()}"></div>`
          ).join("")}
        </div>
      </div>

      <div class="separator"></div>

      <div class="status-group">
        <span class="status-label">FUEL</span>
        <span class="status-value ${fuelClass}">${fuel.toFixed(0)}%</span>
        <div class="mini-bar">
          <div class="mini-bar-fill ${fuelClass}" style="width: ${fuel}%"></div>
        </div>
      </div>

      <div class="separator"></div>

      <div class="status-group">
        <span class="status-label">AMMO</span>
        <span class="status-value ${ammo.cls}">${ammo.text}</span>
      </div>

      <div class="separator"></div>

      <div class="status-group">
        <span class="status-label">VEL</span>
        <span class="status-value info">${this._formatSpeed(speed)}</span>
      </div>

      ${this._getCrewFatigueHtml(ship)}
      ${this._getIrSignatureHtml(ship)}
      ${this._getThermalHtml(ship)}
      ${this._getOpsHtml(ship)}
      ${this._getEcmHtml(ship)}
      ${this._getEngineeringHtml(ship)}
      ${this._getCommsHtml(ship)}
      ${this._getFleetHtml(ship)}
      ${this._getProposalBadgeHtml(ship)}
    `;
  }

  _getIrSignatureHtml(ship) {
    const emissions = ship.emissions;
    if (!emissions) return "";

    const level = emissions.ir_level || "low";
    const coldDrift = emissions.cold_drift_active;
    const cooling = emissions.plume_cooling;

    const levelMap = {
      minimal: { label: "MIN", cls: "nominal" },
      low: { label: "LOW", cls: "nominal" },
      moderate: { label: "MED", cls: "warning" },
      high: { label: "HIGH", cls: "warning" },
      extreme: { label: "MAX", cls: "critical" },
    };

    const info = levelMap[level] || levelMap.low;
    let extra = "";
    if (coldDrift) extra = " COLD";
    else if (cooling) extra = " COOL";

    return `
      <div class="separator"></div>
      <div class="status-group">
        <span class="status-label">IR</span>
        <span class="status-value ${info.cls}">${info.label}${extra}</span>
      </div>
    `;
  }

  _getThermalHtml(ship) {
    const thermal = ship.thermal;
    if (!thermal || !thermal.enabled) return "";
    const temp = thermal.hull_temperature ?? 300;
    const maxTemp = thermal.max_temperature ?? 500;
    const pct = Math.min(100, ((temp - 2.7) / (maxTemp - 2.7)) * 100);
    const cls = thermal.is_emergency ? "critical"
      : thermal.is_overheating ? "warning"
      : temp > (thermal.nominal_temperature ?? 300) + 20 ? "warning"
      : "nominal";
    return `
      <div class="separator"></div>
      <div class="status-group">
        <span class="status-label">TEMP</span>
        <span class="status-value ${cls}">${temp.toFixed(0)}K</span>
        <div class="mini-bar">
          <div class="mini-bar-fill ${cls}" style="width: ${pct}%"></div>
        </div>
      </div>
    `;
  }

  _getOpsHtml(ship) {
    const ops = ship.ops;
    if (!ops || !ops.enabled) return "";

    const teams = ops.repair_teams || [];
    const activeTeams = teams.filter(t => t.status !== "idle");
    const shutdowns = ops.shutdown_systems || [];

    if (activeTeams.length === 0 && shutdowns.length === 0) return "";

    let parts = [];
    if (activeTeams.length > 0) {
      const cls = activeTeams.some(t => t.status === "repairing") ? "warning" : "info";
      parts.push(`<span class="status-value ${cls}">DC:${activeTeams.length}</span>`);
    }
    if (shutdowns.length > 0) {
      parts.push(`<span class="status-value critical">SCRAM:${shutdowns.length}</span>`);
    }

    return `
      <div class="separator"></div>
      <div class="status-group">
        <span class="status-label">OPS</span>
        ${parts.join(" ")}
      </div>
    `;
  }

  _getEcmHtml(ship) {
    const ecm = ship.ecm;
    if (!ecm || !ecm.enabled) return "";

    const modes = [];
    if (ecm.emcon_active) modes.push("EMCON");
    if (ecm.jammer_enabled) modes.push("JAM");
    if (ecm.chaff_active) modes.push("CHF");
    if (ecm.flare_active) modes.push("FLR");

    if (modes.length === 0) return "";

    const cls = ecm.emcon_active ? "info" : "warning";
    return `
      <div class="separator"></div>
      <div class="status-group">
        <span class="status-label">ECM</span>
        <span class="status-value ${cls}">${modes.join(" ")}</span>
      </div>
    `;
  }

  _getEngineeringHtml(ship) {
    const eng = ship.engineering;
    if (!eng || !eng.enabled) return "";

    const parts = [];
    // Show reactor output if not at 100%
    const rPct = eng.reactor_percent ?? (eng.reactor_output ?? 1) * 100;
    if (rPct < 99) {
      const cls = rPct < 50 ? "warning" : "info";
      parts.push(`<span class="status-value ${cls}">RX:${rPct.toFixed(0)}%</span>`);
    }
    // Show drive limit if not at 100%
    const dPct = eng.drive_limit_percent ?? (eng.drive_limit ?? 1) * 100;
    if (dPct < 99) {
      parts.push(`<span class="status-value warning">DRV:${dPct.toFixed(0)}%</span>`);
    }
    // Show radiator state if retracted
    if (eng.radiators_deployed === false) {
      parts.push(`<span class="status-value critical">RAD:RETR</span>`);
    } else if (eng.radiator_priority && eng.radiator_priority !== "balanced") {
      const cls = eng.radiator_priority === "stealth" ? "info" : "nominal";
      parts.push(`<span class="status-value ${cls}">RAD:${eng.radiator_priority.toUpperCase().slice(0, 4)}</span>`);
    }
    // Show emergency vent if active
    if (eng.emergency_vent_active) {
      parts.push(`<span class="status-value critical">VENT</span>`);
    }

    if (parts.length === 0) return "";
    return `
      <div class="separator"></div>
      <div class="status-group">
        <span class="status-label">ENG</span>
        ${parts.join(" ")}
      </div>
    `;
  }

  _getCommsHtml(ship) {
    const comms = ship.comms;
    if (!comms || !comms.enabled) return "";

    const parts = [];
    if (comms.distress_active) parts.push("DISTRESS");
    else if (comms.emcon_suppressed) parts.push("EMCON");
    else if (!comms.transponder_enabled) parts.push("SILENT");

    if (comms.transponder_active) {
      parts.push(`IFF:${(comms.transponder_code || "---").slice(0, 6)}`);
    }

    if (parts.length === 0) return "";

    const cls = comms.distress_active ? "critical" : comms.emcon_suppressed ? "info" : "nominal";
    return `
      <div class="separator"></div>
      <div class="status-group">
        <span class="status-label">COM</span>
        <span class="status-value ${cls}">${parts.join(" ")}</span>
      </div>
    `;
  }

  _getCrewFatigueHtml(ship) {
    const cf = ship.crew_fatigue || ship.systems?.crew_fatigue;
    if (!cf || !cf.enabled) return "";

    const fatigue = cf.fatigue ?? 0;
    const perf = cf.performance ?? 1;
    const gLoad = cf.g_load ?? 0;
    const isBlackedOut = cf.is_blacked_out ?? false;

    if (isBlackedOut) {
      return `
        <div class="separator"></div>
        <div class="status-group">
          <span class="status-label">CREW</span>
          <span class="status-value critical">BLACKOUT</span>
        </div>
      `;
    }

    if (fatigue < 0.3 && gLoad < 3) return "";

    const parts = [];
    if (fatigue > 0.5) {
      const cls = fatigue > 0.7 ? "critical" : "warning";
      parts.push(`<span class="status-value ${cls}">${(perf * 100).toFixed(0)}%</span>`);
    }
    if (gLoad > 5) {
      const cls = gLoad > 7 ? "critical" : "warning";
      parts.push(`<span class="status-value ${cls}">${gLoad.toFixed(1)}g</span>`);
    } else if (gLoad > 3) {
      parts.push(`<span class="status-value info">${gLoad.toFixed(1)}g</span>`);
    }
    if (cf.rest_ordered) {
      parts.push(`<span class="status-value nominal">REST</span>`);
    }

    if (parts.length === 0) return "";

    return `
      <div class="separator"></div>
      <div class="status-group">
        <span class="status-label">CREW</span>
        ${parts.join(" ")}
      </div>
    `;
  }

  _getFleetHtml(ship) {
    const fc = ship.fleet_coord || ship.systems?.fleet_coord;
    if (!fc || !fc.enabled) return "";

    const fleetCount = fc.fleet_count ?? 0;
    if (fleetCount === 0) return "";

    const fleets = fc.fleets || [];
    const activeFleet = fleets[0];
    const shipCount = activeFleet?.ship_count ?? 0;
    const status = activeFleet?.status ?? "forming";

    const statusMap = {
      forming: { label: "FORM", cls: "info" },
      in_formation: { label: "FMT", cls: "nominal" },
      maneuvering: { label: "MNV", cls: "warning" },
      engaging: { label: "ENGAG", cls: "critical" },
      scattered: { label: "SCAT", cls: "warning" },
      disbanded: { label: "DISB", cls: "info" },
    };

    const info = statusMap[status] || { label: status.toUpperCase().slice(0, 5), cls: "info" };

    return `
      <div class="separator"></div>
      <div class="status-group">
        <span class="status-label">FLT</span>
        <span class="status-value ${info.cls}">${info.label} ${shipCount}S</span>
      </div>
    `;
  }

  _getProposalBadgeHtml(ship) {
    // Only show in CPU-ASSIST tier
    const tier = window.controlTier || "raw";
    if (tier !== "cpu-assist") return "";

    // Count pending proposals across all 6 auto-systems
    const systems = [
      "auto_tactical", "auto_ops", "auto_engineering",
      "auto_science", "auto_comms", "auto_fleet"
    ];
    let total = 0;
    for (const key of systems) {
      const sys = ship?.[key];
      if (sys?.enabled && sys?.proposals) {
        total += sys.proposals.length;
      }
    }

    if (total === 0) return "";

    return `
      <div class="separator"></div>
      <div class="status-group">
        <span class="proposal-badge">
          <span class="badge-dot"></span>
          <span class="badge-num">${total}</span> PENDING
        </span>
      </div>
    `;
  }

  _getHullPercent(ship) {
    let percent = ship.hull_percent;
    if (percent === undefined && ship.hull_integrity !== undefined && ship.max_hull_integrity) {
      percent = (ship.hull_integrity / ship.max_hull_integrity) * 100;
    }
    return percent ?? ship.hull ?? 100;
  }

  _getFuelPercent(ship) {
    const propulsion = ship.systems?.propulsion || {};
    const fuelMass = propulsion.fuel_level ?? ship.fuel_mass ?? ship.fuel ?? 0;
    const fuelCapacity = propulsion.max_fuel ?? ship.fuel_capacity ?? 10000;
    return fuelCapacity > 0 ? (fuelMass / fuelCapacity) * 100 : 0;
  }

  _getAmmoSummary(ship) {
    const weapons = ship.systems?.weapons || ship.weapons || {};
    const combat = ship.systems?.combat || ship.combat || {};
    const truthWeapons = weapons.truth_weapons || combat.truth_weapons || {};

    // Aggregate truth weapons by type
    let railgunAmmo = 0, railgunMax = 0;
    let pdcAmmo = 0, pdcMax = 0;

    for (const [mountId, w] of Object.entries(truthWeapons)) {
      const ammo = w.ammo ?? 0;
      const capacity = w.ammo_capacity ?? 0;
      if (mountId.startsWith("railgun")) {
        railgunAmmo += ammo;
        railgunMax += capacity;
      } else if (mountId.startsWith("pdc")) {
        pdcAmmo += ammo;
        pdcMax += capacity;
      }
    }

    // Fallback to legacy torpedo data if no truth weapons found
    if (railgunMax === 0 && pdcMax === 0) {
      const torpedoes = weapons.torpedoes || weapons.torpedo || ship.torpedoes || {};
      const pdc = weapons.pdc || weapons.point_defense || ship.pdc || {};
      railgunAmmo = torpedoes.loaded ?? torpedoes.count ?? torpedoes.ammo ?? 0;
      railgunMax = torpedoes.max ?? torpedoes.capacity ?? 12;
      pdcAmmo = pdc.ammo ?? pdc.rounds ?? 0;
      pdcMax = pdc.max ?? pdc.capacity ?? 1000;
    }

    // Torpedo count from combat system
    const torpedoData = combat.torpedoes || {};
    const torpLoaded = torpedoData.loaded ?? 0;
    const torpTotal = torpedoData.total_capacity ?? 0;

    const railPercent = railgunMax > 0 ? (railgunAmmo / railgunMax) * 100 : 100;
    const pdcPercent = pdcMax > 0 ? (pdcAmmo / pdcMax) * 100 : 100;
    const minPercent = Math.min(railPercent, pdcPercent);

    const cls = minPercent > 50 ? "nominal" : minPercent > 20 ? "warning" : "critical";

    const torpStr = torpTotal > 0 ? ` T:${torpLoaded}` : "";
    return { text: `R:${railgunAmmo} P:${pdcAmmo}${torpStr}`, cls };
  }

  _getSubsystems(ship) {
    const systemsStatus = ship.systems_status || ship.systems || {};
    const result = [];
    const priority = ["propulsion", "sensors", "weapons", "navigation", "power"];

    for (const key of priority) {
      const status = systemsStatus[key];
      if (status !== undefined) {
        result.push({
          name: key.charAt(0).toUpperCase() + key.slice(1),
          status: this._normalizeStatus(status)
        });
      }
    }

    // If none found from systems_status, use defaults
    if (result.length === 0) {
      for (const key of priority) {
        result.push({ name: key.charAt(0).toUpperCase() + key.slice(1), status: "online" });
      }
    }

    return result;
  }

  _normalizeStatus(status) {
    if (typeof status === "boolean") return status ? "online" : "offline";
    if (typeof status === "string") {
      const s = status.toLowerCase();
      if (["on", "active", "ready", "idle", "online"].includes(s)) return "online";
      if (["off", "inactive", "disabled", "offline"].includes(s)) return "offline";
      if (["warning", "degraded", "no_fuel"].includes(s)) return "warning";
      if (["error", "failed", "critical"].includes(s)) return "error";
      return "online";
    }
    if (typeof status === "object" && status !== null) {
      if (status.enabled === false) return "offline";
      if (status.status) {
        const s = String(status.status).toLowerCase();
        if (["error", "failed", "critical"].includes(s)) return "error";
        if (["warning", "degraded", "no_fuel"].includes(s)) return "warning";
        if (["offline", "off", "disabled"].includes(s)) return "offline";
      }
      return "online";
    }
    return "offline";
  }

  _formatSpeed(mps) {
    if (mps >= 1000) return `${(mps / 1000).toFixed(1)} km/s`;
    return `${mps.toFixed(0)} m/s`;
  }
}

customElements.define("status-bar", StatusBar);
export { StatusBar };
