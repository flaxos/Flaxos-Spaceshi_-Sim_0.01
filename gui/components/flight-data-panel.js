/**
 * Flight Data Panel — merged nav display + delta-V budget.
 * Read-only. Tier-aware: raw (m/m/s/kg, component vectors),
 * arcade (friendly km/km/s, combined velocity+heading),
 * cpu-assist (speed + fuel % only).
 */
import { stateManager } from "../js/state-manager.js";
import { extractAutopilotState } from "../js/autopilot-utils.js";

const G0 = 9.81;
const BINGO_PCT = 0.10;

class FlightDataPanel extends HTMLElement {
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
:host { display:block; font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.8rem; font-variant-numeric:tabular-nums; }
.s { padding:10px 14px; }
.s+.s { border-top:1px solid var(--border-default,#2a2a3a); }
.st { font-family:var(--font-sans,"Inter",sans-serif); font-size:.65rem; font-weight:600; text-transform:uppercase; letter-spacing:.5px; color:var(--text-secondary,#888899); margin-bottom:6px; }
.kv { display:flex; justify-content:space-between; align-items:baseline; padding:2px 0; }
.kl { font-family:var(--font-sans,"Inter",sans-serif); font-size:.7rem; color:var(--text-dim,#555566); }
.kv-v { font-variant-numeric:tabular-nums; color:var(--text-primary,#e0e0e0); text-align:right; }
.kv-v.i { color:var(--status-info,#00aaff); }
.kv-v.c { color:var(--status-critical,#ff4444); }
.fb { height:14px; background:var(--bg-input,#1a1a24); border-radius:3px; overflow:hidden; position:relative; margin-top:4px; }
.ff { height:100%; transition:width .3s ease; border-radius:3px; }
.ff.g { background:var(--status-nominal,#00ff88); }
.ff.a { background:var(--status-warning,#ffaa00); }
.ff.r { background:var(--status-critical,#ff4444); }
.ft { position:absolute; right:6px; top:50%; transform:translateY(-50%); font-size:.65rem; color:var(--text-bright,#fff); text-shadow:0 1px 2px rgba(0,0,0,.5); }
.bingo { padding:6px; background:rgba(255,68,68,.15); border:1px solid var(--status-critical,#ff4444); border-radius:4px; text-align:center; font-weight:700; font-size:.75rem; color:var(--status-critical,#ff4444); letter-spacing:2px; animation:bp 1.5s ease-in-out infinite; margin-bottom:6px; }
.ponr { padding:6px; border-radius:4px; text-align:center; font-weight:700; font-size:.7rem; letter-spacing:1px; margin-bottom:6px; }
.ponr.warn { background:rgba(255,170,0,.12); border:1px solid var(--status-warning,#ffaa00); color:var(--status-warning,#ffaa00); }
.ponr.crit { background:rgba(255,68,68,.15); border:1px solid var(--status-critical,#ff4444); color:var(--status-critical,#ff4444); animation:bp 1s ease-in-out infinite; }
.ponr.ok { background:rgba(0,255,136,.08); border:1px solid var(--status-nominal,#00ff88); color:var(--status-nominal,#00ff88); }
@keyframes bp { 0%,100%{opacity:1} 50%{opacity:.5} }
.empty { text-align:center; color:var(--text-dim,#555566); padding:24px; font-style:italic; font-size:.75rem; }
.hero { text-align:center; padding:14px; }
.bp-phase { display:inline-block; padding:1px 6px; border-radius:3px; font-size:.6rem; font-weight:700; letter-spacing:1px; margin-bottom:4px; }
.bp-phase.burn  { background:rgba(255,170,0,.2); color:var(--status-warning,#ffaa00); }
.bp-phase.flip  { background:rgba(204,102,255,.2); color:#cc66ff; }
.bp-phase.brake { background:rgba(255,68,68,.2); color:var(--status-critical,#ff4444); }
.bp-phase.approach { background:rgba(0,170,255,.2); color:var(--status-info,#00aaff); }
.bp-phase.stationkeep { background:rgba(0,255,136,.15); color:var(--status-nominal,#00ff88); }
.flip-soon { color:var(--status-warning,#ffaa00); font-weight:600; }
.hero .hv { font-size:1.6rem; font-weight:700; color:var(--status-info,#00aaff); }
.hero .hs { font-size:.75rem; color:var(--text-secondary,#888899); margin-top:2px; }
:host(.tier-raw) .s+.s { border-color:#00ff8833; }
:host(.tier-raw) .st { font-family:"Courier New",monospace; color:#00ff8866; border-bottom:1px solid #00ff8822; padding-bottom:3px; }
:host(.tier-raw) .kl { font-family:"Courier New",monospace; color:#00ff8888; }
:host(.tier-raw) .kv-v { font-family:"Courier New",monospace; color:#00ff88; text-shadow:0 0 4px #00ff8844; }
@media(max-width:400px) { .s{padding:8px 10px} .kl{font-size:.65rem} }
</style><div id="c"><div class="empty">Waiting for flight data...</div></div>`;
    this.classList.remove("tier-raw", "tier-arcade", "tier-cpu-assist");
    this.classList.add(`tier-${this._tier}`);
  }

  _gather() {
    const nav = stateManager.getNavigation();
    const ship = stateManager.getShipState();
    if (!ship || Object.keys(ship).length === 0) return null;
    const pos = nav.position || [0, 0, 0];
    const vel = nav.velocity || [0, 0, 0];
    const hdg = nav.heading || { pitch: 0, yaw: 0 };
    const vmag = ship.navigation?.velocity_magnitude ?? ship.velocity_magnitude ?? this._mag(vel);
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
    const tg = prop.thrust_g || 0;
    const th = prop.throttle ?? 0;
    const ct = mt * th;
    let bt = null;
    if (ct > 0 && ve > 0) { const r = ct / ve; bt = r > 0 ? fm / r : null; }
    // Point-of-no-return data (from server telemetry or client-side fallback)
    const ponr = ship.ponr || null;
    // Autopilot burn-plan data (null when manual flight)
    const ap = extractAutopilotState();
    return { pos, vel, hdg, vmag, fm, fc, fp, dm, wm, dv, tg, bt, ponr, ap };
  }

  _update() {
    const el = this.shadowRoot.getElementById("c");
    const d = this._gather();
    if (!d) { el.innerHTML = '<div class="empty">Waiting for flight data...</div>'; return; }
    const fn = this._tier === "raw" ? this._rawHTML(d)
      : this._tier === "cpu-assist" ? this._assistHTML(d) : this._arcadeHTML(d);
    el.innerHTML = fn;
  }

  // -- kv-inline helper to reduce template repetition --
  _kv(label, value, cls = "") {
    return `<div class="kv"><span class="kl">${label}</span><span class="kv-v ${cls}">${value}</span></div>`;
  }

  _fuelBar(fp, fmLabel) {
    const cc = fp > .5 ? "g" : fp > .25 ? "a" : "r";
    return `<div class="fb"><div class="ff ${cc}" style="width:${(fp*100).toFixed(1)}%"></div>${fmLabel ? `<span class="ft">${fmLabel}</span>` : ""}</div>`;
  }

  _bingoHTML(fp, fc) {
    return (fp < BINGO_PCT && fc > 0) ? '<div class="bingo">BINGO FUEL</div>' : "";
  }

  _ponrHTML(ponr, compact = false) {
    if (!ponr) return "";
    if (ponr.past_ponr) {
      return '<div class="ponr crit">PAST POINT OF NO RETURN</div>';
    }
    if (ponr.margin_percent < 25 && ponr.dv_to_stop > 0) {
      const label = compact ? "PONR" : "BRAKING MARGIN";
      return `<div class="ponr warn">${label}: ${ponr.margin_percent.toFixed(0)}% \u2014 ${this._fmtSpd(ponr.dv_margin)} reserve</div>`;
    }
    return "";
  }

  /** Burn-plan section — shown when a flip-and-burn AP is active.
   *  Programs: rendezvous, intercept, goto_position, dock_approach.
   *  Returns "" when manual or for hold/match/evasive programs. */
  _burnPlanHTML(ap, compact = false) {
    if (!ap) return "";
    const BURN_PROGRAMS = ["rendezvous", "intercept", "approach", "dock_approach",
                           "goto_position", "set_course", "course"];
    const prog = (ap.program || "").toLowerCase();
    if (!BURN_PROGRAMS.includes(prog)) return "";

    const phase = (ap.phase || "").toLowerCase();
    const phaseClass = ["burn","flip","brake"].includes(phase) ? phase
      : phase.startsWith("approach") ? "approach"
      : phase === "stationkeep" ? "stationkeep" : "";
    const phaseLabel = phase.replace(/_/g, " ").toUpperCase() || "ACTIVE";

    const rows = [];

    if (!compact) {
      // Range + closing speed always useful
      if (ap.range != null)
        rows.push(this._kv("Range", this._fmtDist(ap.range)));
      if (ap.closingSpeed != null && ap.closingSpeed > 0.1)
        rows.push(this._kv("Closing", this._fmtSpd(ap.closingSpeed), "i"));
    }

    // Flip countdown — only meaningful in BURN phase
    if (phase === "burn" && ap.flipInM != null && ap.flipInS != null) {
      const dist = this._fmtDist(ap.flipInM);
      const t = this._fmtDur(ap.flipInS);
      rows.push(`<div class="kv"><span class="kl">Flip in</span><span class="kv-v flip-soon">${dist} / ~${t}</span></div>`);
    } else if (phase === "burn" && ap.flipTriggerRangeM != null) {
      // Still building speed, flip trigger range at least
      rows.push(this._kv("Flip at", this._fmtDist(ap.flipTriggerRangeM)));
    }

    // Braking distance — useful in BRAKE phase
    if (phase === "brake" && ap.brakingDistance != null)
      rows.push(this._kv("Brake dist", this._fmtDist(ap.brakingDistance)));

    // ETA always useful when non-trivial
    if (ap.eta != null && ap.eta > 5)
      rows.push(this._kv("ETA", this._fmtDur(ap.eta), "i"));

    if (!phaseClass && rows.length === 0) return "";

    const badge = phaseClass
      ? `<span class="bp-phase ${phaseClass}">${phaseLabel}</span>`
      : `<span class="bp-phase">${phaseLabel}</span>`;

    return `<div class="s"><div class="st">Nav Plan ${badge}</div>${rows.join("")}</div>`;
  }

  // -- ARCADE --
  _arcadeHTML(d) {
    return `${this._burnPlanHTML(d.ap)}<div class="s"><div class="st">Position</div>${
      this._kv("X", this._fmtDist(d.pos[0]))}${
      this._kv("Y", this._fmtDist(d.pos[1]))}${
      this._kv("Z", this._fmtDist(d.pos[2]))
    }</div><div class="s"><div class="st">Velocity</div>${
      this._kv("Speed", this._fmtSpd(d.vmag), "i")}${
      this._kv("Heading", this._fmtAng(d.hdg.yaw ?? 0))}${
      d.tg > 0 ? this._kv("Accel", d.tg.toFixed(2) + " G") : ""
    }</div><div class="s">${this._ponrHTML(d.ponr)}${this._bingoHTML(d.fp, d.fc)}${
      this._kv("\u0394v", this._fmtSpd(d.dv), "i")}${
      d.ponr && d.ponr.dv_to_stop > 0 ? this._kv("\u0394v to stop", this._fmtSpd(d.ponr.dv_to_stop)) : ""}${
      this._kv("Fuel", (d.fp*100).toFixed(1) + "%", d.fp < .25 ? "c" : "")}${
      this._fuelBar(d.fp, this._fmtMass(d.fm))}${
      d.bt !== null ? this._kv("Burn time", this._fmtDur(d.bt)) : ""}${
      d.ponr && d.ponr.stop_time > 0 && d.ponr.dv_to_stop > 0 ? this._kv("Stop dist", this._fmtDist(d.ponr.stop_distance)) : ""}${
      this._kv("Mass", this._fmtMass(d.wm))
    }</div>`;
  }

  // -- RAW --
  _rawHTML(d) {
    const ac = (d.tg * G0).toFixed(2);
    return `${this._burnPlanHTML(d.ap)}<div class="s"><div class="st">VELOCITY (m/s)</div>${
      this._kv("Vx", this._sf(d.vel[0]))}${
      this._kv("Vy", this._sf(d.vel[1]))}${
      this._kv("Vz", this._sf(d.vel[2]))}${
      this._kv("MAG", d.vmag.toFixed(1), "i")
    }</div><div class="s"><div class="st">POSITION (m)</div>${
      this._kv("X", this._sf(d.pos[0]))}${
      this._kv("Y", this._sf(d.pos[1]))}${
      this._kv("Z", this._sf(d.pos[2]))
    }</div><div class="s"><div class="st">ACCEL</div>${
      this._kv("FWD", ac + " m/s\u00B2")
    }</div><div class="s">${this._ponrHTML(d.ponr)}${this._bingoHTML(d.fp, d.fc)}<div class="st">DELTA-V / FUEL</div>${
      this._kv("dV", d.dv.toFixed(1) + " m/s", "i")}${
      d.ponr ? this._kv("dV_STOP", d.ponr.dv_to_stop.toFixed(1) + " m/s") : ""}${
      d.ponr ? this._kv("MARGIN", d.ponr.dv_margin.toFixed(1) + " m/s", d.ponr.past_ponr ? "c" : "") : ""}${
      this._kv("FUEL", d.fm.toFixed(1) + " kg")}${
      this._fuelBar(d.fp, (d.fp*100).toFixed(1) + "%")}${
      d.bt !== null ? this._kv("BURN", this._fmtDur(d.bt)) : ""}${
      d.ponr && d.ponr.stop_time > 0 ? this._kv("T_STOP", d.ponr.stop_time.toFixed(1) + " s") : ""}${
      d.ponr && d.ponr.stop_distance > 0 ? this._kv("D_STOP", d.ponr.stop_distance.toFixed(0) + " m") : ""}${
      this._kv("DRY", d.dm.toFixed(1) + " kg")}${
      this._kv("WET", d.wm.toFixed(1) + " kg")
    }</div>`;
  }

  // -- CPU-ASSIST --
  _assistHTML(d) {
    return `${this._burnPlanHTML(d.ap, true)}<div class="hero"><div class="hv">${this._fmtSpd(d.vmag)}</div><div class="hs">current speed</div></div><div class="s">${
      this._ponrHTML(d.ponr, true)}${
      this._bingoHTML(d.fp, d.fc)}${
      this._kv("\u0394v", this._fmtSpd(d.dv), "i")}${
      this._kv("Fuel", (d.fp*100).toFixed(0) + "%", d.fp < .25 ? "c" : "")}${
      this._fuelBar(d.fp, null)
    }</div>`;
  }

  // -- Format helpers --
  _mag(v) { return Math.sqrt(v[0]**2 + v[1]**2 + v[2]**2); }

  /** Distance: <1000 -> "850 m", >=1000 -> "1.2 km", >=1e6 -> "1,234 km" */
  _fmtDist(m) {
    const a = Math.abs(m);
    if (a >= 1e6) return (a/1000).toLocaleString(undefined, {maximumFractionDigits:0}) + " km";
    if (a >= 1000) return (a/1000).toFixed(1) + " km";
    return a.toFixed(0) + " m";
  }

  /** Speed: <100 -> "42.3 m/s", >=100 -> "142 m/s", >=1000 -> "1.24 km/s" */
  _fmtSpd(v) {
    const a = Math.abs(v);
    if (a >= 1000) return (a/1000).toFixed(2) + " km/s";
    if (a >= 100) return a.toFixed(0) + " m/s";
    return a.toFixed(1) + " m/s";
  }

  _fmtAng(deg) { return `${deg >= 0 ? "+" : ""}${deg.toFixed(1)}\u00B0`; }

  _fmtMass(kg) {
    if (kg >= 1000) return (kg/1000).toLocaleString(undefined, {maximumFractionDigits:1}) + " t";
    return kg.toLocaleString(undefined, {maximumFractionDigits:0}) + " kg";
  }

  _fmtDur(s) {
    const t = Math.max(0, Math.floor(s));
    const h = Math.floor(t/3600), m = Math.floor((t%3600)/60), sc = t%60;
    if (h > 0) return `${h}h ${String(m).padStart(2,"0")}m ${String(sc).padStart(2,"0")}s`;
    if (m > 0) return `${m}m ${String(sc).padStart(2,"0")}s`;
    return `${sc}s`;
  }

  /** Signed fixed-point: "+1234.5" / "-42.0" */
  _sf(v, d = 1) { return `${v >= 0 ? "+" : ""}${v.toFixed(d)}`; }
}

customElements.define("flight-data-panel", FlightDataPanel);
export { FlightDataPanel };
