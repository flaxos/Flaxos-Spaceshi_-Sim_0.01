/**
 * Helm Navigation Display
 * Comprehensive navigation readout for the helm station: velocity vector,
 * acceleration, orientation, fuel/delta-v budget, trajectory projection
 * (1/5/10 min), intercept calculator, and flip-and-burn indicators.
 * All values in physical units (km, km/s, g, kg).
 */
import { stateManager } from "../js/state-manager.js";

const G0 = 9.81;

class HelmNavDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._tier = window.controlTier || "arcade";
    this._onTier = (e) => {
      const t = e.detail?.tier || "arcade";
      if (t !== this._tier) { this._tier = t; this._init(); this._update(); }
    };
  }

  connectedCallback() {
    this._init();
    this._unsub = stateManager.subscribe("*", () => this._update());
    document.addEventListener("tier-change", this._onTier);
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; }
    document.removeEventListener("tier-change", this._onTier);
  }

  _init() {
    this.shadowRoot.innerHTML = `<style>
:host { display:block; font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.78rem; font-variant-numeric:tabular-nums; }
.sec { padding:10px 14px; }
.sec+.sec { border-top:1px solid var(--border-default,#2a2a3a); }
.st { font-family:var(--font-sans,"Inter",sans-serif); font-size:.65rem; font-weight:600; text-transform:uppercase; letter-spacing:.5px; color:var(--text-secondary,#888899); margin-bottom:6px; }
.kv { display:flex; justify-content:space-between; align-items:baseline; padding:2px 0; }
.kl { font-family:var(--font-sans,"Inter",sans-serif); font-size:.7rem; color:var(--text-dim,#555566); }
.kv-v { font-variant-numeric:tabular-nums; color:var(--text-primary,#e0e0e0); text-align:right; }
.kv-v.i { color:var(--status-info,#00aaff); }
.kv-v.n { color:var(--status-nominal,#00ff88); }
.kv-v.w { color:var(--status-warning,#ffaa00); }
.kv-v.c { color:var(--status-critical,#ff4444); }
.hero { text-align:center; padding:10px 0 6px; }
.hero .hv { font-size:1.5rem; font-weight:700; color:var(--status-info,#00aaff); }
.hero .hs { font-size:.7rem; color:var(--text-secondary,#888899); margin-top:2px; }
.orient-row { display:flex; justify-content:center; gap:16px; padding:4px 0 2px; }
.orient-row span { font-size:.75rem; color:var(--text-secondary,#888899); }
.fb { height:14px; background:var(--bg-input,#1a1a24); border-radius:3px; overflow:hidden; position:relative; margin-top:4px; }
.ff { height:100%; transition:width .3s ease; border-radius:3px; }
.ff.g { background:var(--status-nominal,#00ff88); }
.ff.a { background:var(--status-warning,#ffaa00); }
.ff.r { background:var(--status-critical,#ff4444); }
.ft { position:absolute; right:6px; top:50%; transform:translateY(-50%); font-size:.65rem; color:var(--text-bright,#fff); text-shadow:0 1px 2px rgba(0,0,0,.5); }
.traj-row { display:flex; justify-content:space-between; padding:2px 0; font-size:.7rem; }
.traj-t { color:var(--text-secondary,#888899); min-width:50px; }
.traj-pos { color:var(--text-dim,#555566); text-align:right; }
.traj-dist { color:var(--text-primary,#e0e0e0); min-width:80px; text-align:right; }
.alert { padding:6px; border-radius:4px; text-align:center; font-weight:700; font-size:.7rem; letter-spacing:1px; margin-bottom:6px; }
.alert.crit { background:rgba(255,68,68,.15); border:1px solid var(--status-critical,#ff4444); color:var(--status-critical,#ff4444); animation:bp 1s ease-in-out infinite; }
.alert.warn { background:rgba(255,170,0,.12); border:1px solid var(--status-warning,#ffaa00); color:var(--status-warning,#ffaa00); }
.alert.ok { background:rgba(0,255,136,.08); border:1px solid var(--status-nominal,#00ff88); color:var(--status-nominal,#00ff88); }
.flip-ind { display:flex; align-items:center; gap:8px; padding:6px 10px; background:rgba(0,170,255,.08); border:1px solid var(--status-info,#00aaff); border-radius:4px; margin-bottom:6px; }
.flip-ind.active { background:rgba(255,170,0,.12); border-color:var(--status-warning,#ffaa00); }
.flip-ind.urgent { background:rgba(255,68,68,.15); border-color:var(--status-critical,#ff4444); animation:bp 1.2s ease-in-out infinite; }
.flip-label { font-size:.65rem; text-transform:uppercase; letter-spacing:.5px; color:var(--text-secondary,#888899); }
.flip-val { font-size:.85rem; font-weight:600; color:var(--status-info,#00aaff); }
.flip-ind.active .flip-val { color:var(--status-warning,#ffaa00); }
.flip-ind.urgent .flip-val { color:var(--status-critical,#ff4444); }
.intercept { padding:8px; background:rgba(0,0,0,.2); border:1px solid var(--border-default,#2a2a3a); border-radius:4px; }
.intercept .ic-label { font-size:.6rem; text-transform:uppercase; color:var(--text-dim,#555566); margin-bottom:4px; }
.drift-badge { display:inline-block; padding:2px 8px; border-radius:3px; font-size:.65rem; font-weight:600; letter-spacing:.5px; }
.drift-badge.on-axis { background:rgba(0,255,136,.12); color:var(--status-nominal,#00ff88); }
.drift-badge.drifting { background:rgba(255,170,0,.12); color:var(--status-warning,#ffaa00); }
.drift-badge.sideways { background:rgba(255,68,68,.12); color:var(--status-critical,#ff4444); }
.empty { text-align:center; color:var(--text-dim,#555566); padding:24px; font-style:italic; font-size:.75rem; }
@keyframes bp { 0%,100%{opacity:1} 50%{opacity:.5} }
@media(max-width:400px) { .sec{padding:8px 10px} .kl{font-size:.65rem} }
</style><div id="c"><div class="empty">Waiting for navigation data...</div></div>`;
    this.classList.remove("tier-raw", "tier-arcade", "tier-cpu-assist");
    this.classList.add(`tier-${this._tier}`);
  }

  _gather() {
    const ship = stateManager.getShipState();
    if (!ship || Object.keys(ship).length === 0) return null;

    const nav = stateManager.getNavigation();
    const pos = nav.position || [0, 0, 0];
    const vel = nav.velocity || [0, 0, 0];
    const vmag = ship.velocity_magnitude ?? this._mag(vel);
    const amag = ship.acceleration_magnitude ?? 0;
    const orient = ship.orientation || { pitch: 0, yaw: 0, roll: 0 };
    const angVel = ship.angular_velocity || { pitch: 0, yaw: 0, roll: 0 };

    // Propulsion
    const prop = ship.systems?.propulsion || {};
    const fuel = ship.fuel || {};
    const fm = prop.fuel_mass ?? fuel.level ?? fuel.current ?? 0;
    const fc = prop.fuel_capacity ?? fuel.max ?? fuel.capacity ?? 0;
    const fp = fc > 0 ? fm / fc : 0;
    const dm = ship.dry_mass ?? prop.dry_mass ?? ship.mass ?? 0;
    const wm = dm + fm;
    const mt = prop.max_thrust_n ?? prop.max_thrust ?? 0;
    const ve = prop.exhaust_velocity ?? (prop.isp ? prop.isp * G0 : 0);
    let dv = ship.delta_v_remaining ?? prop.delta_v ?? null;
    if (dv === null && ve > 0 && dm > 0 && wm > dm) dv = ve * Math.log(wm / dm);
    dv = dv ?? 0;
    const th = prop.throttle ?? 0;
    const ct = mt * th;
    let bt = null;
    if (ct > 0 && ve > 0) { const r = ct / ve; bt = r > 0 ? fm / r : null; }

    // Trajectory
    const traj = ship.trajectory || {};
    const velHeading = traj.velocity_heading || { pitch: 0, yaw: 0 };
    const drift = traj.drift_angle || 0;
    const maxAccelG = traj.max_accel_g || 0;
    const timeToZero = traj.time_to_zero;
    const projections = traj.projected_positions || [];

    // PONR
    const ponr = ship.ponr || null;

    // Drift state
    const isDrifting = ship.is_drifting || false;

    // Target info for intercept
    const targetId = ship.target_id || null;
    const contacts = ship.sensors?.contacts || [];
    const target = targetId ? contacts.find(c => c.id === targetId) : null;

    // Compute extended projections (1min, 5min, 10min) client-side
    const extProjections = this._computeProjections(pos, vel, ship.acceleration || { x: 0, y: 0, z: 0 });

    // Compute flip-and-burn timing
    const flipBurn = this._computeFlipBurn(vmag, maxAccelG, ponr, target, pos);

    // Compute intercept data if target exists
    const intercept = target ? this._computeIntercept(pos, vel, target, maxAccelG, dv) : null;

    return {
      pos, vel, vmag, amag, orient, angVel,
      fm, fc, fp, dm, wm, dv, bt, th,
      velHeading, drift, maxAccelG, timeToZero,
      projections, extProjections,
      ponr, isDrifting, targetId, target, flipBurn, intercept,
    };
  }

  _computeProjections(pos, vel, accel) {
    const times = [60, 300, 600]; // 1, 5, 10 minutes
    return times.map(t => {
      const px = pos[0] + vel[0] * t + 0.5 * (accel.x || 0) * t * t;
      const py = pos[1] + vel[1] * t + 0.5 * (accel.y || 0) * t * t;
      const pz = pos[2] + vel[2] * t + 0.5 * (accel.z || 0) * t * t;
      const dx = px - pos[0], dy = py - pos[1], dz = pz - pos[2];
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
      return { t, label: t >= 600 ? "10 min" : t >= 300 ? "5 min" : "1 min", pos: [px, py, pz], dist };
    });
  }

  _computeFlipBurn(vmag, maxAccelG, ponr, target, pos) {
    const maxAccel = maxAccelG * G0;
    if (maxAccel <= 0 || vmag < 0.1) return null;

    // Time to decelerate to zero at max thrust
    const tDecel = vmag / maxAccel;
    // Distance covered during deceleration
    const dDecel = 0.5 * vmag * tDecel;

    let flipTime = null;
    let flipDist = null;
    let urgency = "nominal"; // nominal, active, urgent

    if (target) {
      const tgt = target.position || {};
      const dist = target.distance || Math.sqrt(
        (tgt.x - pos[0]) ** 2 + (tgt.y - pos[1]) ** 2 + (tgt.z - pos[2]) ** 2
      );
      if (dist > 0 && vmag > 0.1) {
        // Distance at which to start flipping
        flipDist = dist - dDecel;
        // Time until we need to flip (at current closing rate)
        flipTime = flipDist > 0 ? flipDist / vmag : 0;

        if (flipDist <= 0) urgency = "urgent";
        else if (flipTime < 60) urgency = "active";
      }
    }

    // If no target, show time-to-zero from PONR data
    const ttz = ponr?.stop_time || tDecel;

    return {
      timeToDecel: tDecel,
      decelDist: dDecel,
      flipTime,
      flipDist,
      urgency,
      timeToZero: ttz,
    };
  }

  _computeIntercept(pos, vel, target, maxAccelG, dv) {
    const tgt = target.position || {};
    const tgtVel = target.velocity || {};
    const dist = target.distance || Math.sqrt(
      (tgt.x - pos[0]) ** 2 + (tgt.y - pos[1]) ** 2 + (tgt.z - pos[2]) ** 2
    );

    // Relative velocity
    const rvx = (tgtVel.x || 0) - vel[0];
    const rvy = (tgtVel.y || 0) - vel[1];
    const rvz = (tgtVel.z || 0) - vel[2];
    const relVel = Math.sqrt(rvx * rvx + rvy * rvy + rvz * rvz);

    // Closing rate (negative = closing)
    const dx = tgt.x - pos[0], dy = tgt.y - pos[1], dz = tgt.z - pos[2];
    const distMag = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
    const closingRate = -(dx * rvx + dy * rvy + dz * rvz) / distMag;

    // Estimated time to intercept (simple)
    const eta = closingRate > 0 ? dist / closingRate : null;

    // Delta-v required for intercept (approximation: match relative velocity)
    const dvRequired = relVel;
    const dvSufficient = dv >= dvRequired;

    return {
      dist,
      relVel,
      closingRate,
      eta,
      dvRequired,
      dvSufficient,
      targetId: target.id,
    };
  }

  _update() {
    const el = this.shadowRoot.getElementById("c");
    const d = this._gather();
    if (!d) { el.innerHTML = '<div class="empty">Waiting for navigation data...</div>'; return; }
    el.innerHTML = this._renderHTML(d);
  }

  _kv(label, value, cls = "") {
    return `<div class="kv"><span class="kl">${label}</span><span class="kv-v ${cls}">${value}</span></div>`;
  }

  _renderHTML(d) {
    let html = "";

    // -- Velocity hero --
    html += `<div class="hero"><div class="hv">${this._fmtSpd(d.vmag)}</div>`;
    html += `<div class="hs">${d.isDrifting ? "DRIFTING" : d.th > 0 ? "THRUSTING" : "IDLE"}</div></div>`;

    // -- Orientation --
    html += `<div class="orient-row">`;
    html += `<span>P ${this._fmtAng(d.orient.pitch)}</span>`;
    html += `<span>Y ${this._fmtAng(d.orient.yaw)}</span>`;
    html += `<span>R ${this._fmtAng(d.orient.roll)}</span>`;
    html += `</div>`;

    // -- Velocity & Acceleration section --
    html += `<div class="sec"><div class="st">Velocity & Acceleration</div>`;
    html += this._kv("Speed", this._fmtSpd(d.vmag), "i");
    html += this._kv("Heading", `P${this._fmtAng(d.velHeading.pitch)} Y${this._fmtAng(d.velHeading.yaw)}`);
    const driftCls = d.drift < 5 ? "on-axis" : d.drift < 30 ? "drifting" : "sideways";
    const driftLabel = d.drift < 1 ? "ON-AXIS" : d.drift.toFixed(1) + "\u00B0";
    html += `<div class="kv"><span class="kl">Drift</span><span class="drift-badge ${driftCls}">${driftLabel}</span></div>`;
    html += this._kv("Accel", `${d.amag.toFixed(2)} m/s\u00B2 (${(d.amag / G0).toFixed(2)}G)`, "i");
    html += this._kv("Max Accel", `${d.maxAccelG.toFixed(2)}G`);
    html += `</div>`;

    // -- Flip & Burn Indicator --
    if (d.flipBurn) {
      const fb = d.flipBurn;
      const indClass = fb.urgency === "urgent" ? "urgent" : fb.urgency === "active" ? "active" : "";
      html += `<div class="sec">`;
      html += `<div class="st">Flip & Burn</div>`;

      if (fb.flipTime !== null) {
        html += `<div class="flip-ind ${indClass}">`;
        html += `<div><div class="flip-label">Flip in</div><div class="flip-val">${fb.flipTime <= 0 ? "NOW" : this._fmtDur(fb.flipTime)}</div></div>`;
        html += `<div style="margin-left:auto"><div class="flip-label">Decel dist</div><div class="flip-val">${this._fmtDist(fb.decelDist)}</div></div>`;
        html += `</div>`;
      }
      html += this._kv("Time to zero", this._fmtDur(fb.timeToZero), fb.timeToZero > 300 ? "" : "w");
      html += this._kv("Decel burn", this._fmtDur(fb.timeToDecel));
      html += `</div>`;
    }

    // -- Fuel & Delta-V --
    html += `<div class="sec">`;
    if (d.ponr?.past_ponr) html += `<div class="alert crit">PAST POINT OF NO RETURN</div>`;
    else if (d.ponr && d.ponr.margin_percent < 25 && d.ponr.dv_to_stop > 0) {
      html += `<div class="alert warn">BRAKING MARGIN: ${d.ponr.margin_percent.toFixed(0)}%</div>`;
    }
    html += `<div class="st">Fuel & Delta-V Budget</div>`;
    html += this._kv("\u0394v remaining", this._fmtSpd(d.dv), "i");
    if (d.ponr && d.ponr.dv_to_stop > 0) html += this._kv("\u0394v to stop", this._fmtSpd(d.ponr.dv_to_stop));
    if (d.ponr) html += this._kv("Margin", this._fmtSpd(d.ponr.dv_margin), d.ponr.past_ponr ? "c" : d.ponr.margin_percent < 25 ? "w" : "n");
    html += this._kv("Fuel", `${(d.fp * 100).toFixed(1)}%  (${this._fmtMass(d.fm)})`, d.fp < 0.25 ? "c" : "");
    const fcc = d.fp > 0.5 ? "g" : d.fp > 0.25 ? "a" : "r";
    html += `<div class="fb"><div class="ff ${fcc}" style="width:${(d.fp * 100).toFixed(1)}%"></div><span class="ft">${this._fmtMass(d.fm)}</span></div>`;
    if (d.bt !== null) html += this._kv("Burn time left", this._fmtDur(d.bt));
    html += this._kv("Ship mass", this._fmtMass(d.wm));
    html += this._kv("Dry mass", this._fmtMass(d.dm));
    html += `</div>`;

    // -- Trajectory Projection --
    html += `<div class="sec"><div class="st">Trajectory Projection</div>`;
    for (const p of d.extProjections) {
      html += `<div class="traj-row">`;
      html += `<span class="traj-t">T+${p.label}</span>`;
      html += `<span class="traj-dist">${this._fmtDist(p.dist)} travel</span>`;
      html += `</div>`;
    }
    if (d.projections.length > 0) {
      html += `<div style="margin-top:6px;font-size:.65rem;color:var(--text-dim,#555566)">Server projections (detailed):</div>`;
      for (const p of d.projections) {
        html += `<div class="traj-row">`;
        html += `<span class="traj-t">T+${p.t}s</span>`;
        html += `<span class="traj-pos">${this._fmtPos(p.position)}</span>`;
        html += `</div>`;
      }
    }
    html += `</div>`;

    // -- Intercept Calculator --
    if (d.intercept) {
      const ic = d.intercept;
      html += `<div class="sec"><div class="st">Intercept: ${ic.targetId}</div>`;
      html += `<div class="intercept">`;
      html += this._kv("Distance", this._fmtDist(ic.dist));
      html += this._kv("Rel velocity", this._fmtSpd(ic.relVel));
      html += this._kv("Closing rate", ic.closingRate > 0 ? this._fmtSpd(ic.closingRate) + " closing" : ic.closingRate < -0.1 ? this._fmtSpd(Math.abs(ic.closingRate)) + " opening" : "parallel", ic.closingRate > 0 ? "n" : "w");
      if (ic.eta !== null) html += this._kv("ETA", this._fmtDur(ic.eta), ic.eta < 60 ? "w" : "i");
      html += this._kv("\u0394v to match", this._fmtSpd(ic.dvRequired), ic.dvSufficient ? "n" : "c");
      if (!ic.dvSufficient) html += `<div class="alert warn">INSUFFICIENT \u0394v FOR INTERCEPT</div>`;
      html += `</div></div>`;
    }

    return html;
  }

  // -- Format helpers --
  _mag(v) { return Math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2); }

  _fmtDist(m) {
    const a = Math.abs(m);
    if (a >= 1e6) return (a / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 }) + " km";
    if (a >= 1000) return (a / 1000).toFixed(1) + " km";
    return a.toFixed(0) + " m";
  }

  _fmtSpd(v) {
    const a = Math.abs(v);
    if (a >= 1000) return (a / 1000).toFixed(2) + " km/s";
    if (a >= 100) return a.toFixed(0) + " m/s";
    return a.toFixed(1) + " m/s";
  }

  _fmtAng(deg) { return `${(deg || 0) >= 0 ? "+" : ""}${(deg || 0).toFixed(1)}\u00B0`; }

  _fmtMass(kg) {
    if (kg >= 1000) return (kg / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 }) + " t";
    return kg.toLocaleString(undefined, { maximumFractionDigits: 0 }) + " kg";
  }

  _fmtDur(s) {
    if (s == null || !Number.isFinite(s)) return "---";
    const t = Math.max(0, Math.floor(s));
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sc = t % 60;
    if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m ${String(sc).padStart(2, "0")}s`;
    if (m > 0) return `${m}m ${String(sc).padStart(2, "0")}s`;
    return `${sc}s`;
  }

  _fmtPos(pos) {
    if (!pos) return "---";
    const x = ((pos.x || 0) / 1000).toFixed(1);
    const y = ((pos.y || 0) / 1000).toFixed(1);
    const z = ((pos.z || 0) / 1000).toFixed(1);
    return `${x}, ${y}, ${z} km`;
  }
}

customElements.define("helm-nav-display", HelmNavDisplay);
export { HelmNavDisplay };
