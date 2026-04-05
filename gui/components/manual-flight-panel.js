/**
 * Manual Flight Panel — unified throttle + heading + velocity readout.
 * Tier-aware: RAW=full controls, ARCADE=throttle+readonly heading, CPU-ASSIST=hidden.
 * MANUAL tier adds coordinate navigation section (set_course command).
 * Commands: set_thrust {thrust:0-1}, set_orientation {pitch,yaw,roll}, set_course {x,y,z}.
 */
import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class ManualFlightPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._tier = window.controlTier || "arcade";
    this._throttle = 0; this._isDragging = false; this._pendingThrottle = false;
    this._pitch = 0; this._yaw = 0; this._roll = 0;
    this._currentG = 0; this._maxForceN = 0; this._velocity = [0, 0, 0];
    this._docHandlers = [];
  }

  connectedCallback() {
    this._render();
    this._unsub = stateManager.subscribe("*", () => { if (!this._isDragging) this._updateFromState(); });
    this._setupInteraction();
    this._onTier = (e) => { this._tier = e.detail?.tier || "arcade"; this._applyTier(); };
    document.addEventListener("tier-change", this._onTier);
    this._applyTier();
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; }
    if (this._onTier) { document.removeEventListener("tier-change", this._onTier); this._onTier = null; }
    for (const h of this._docHandlers) document.removeEventListener(h.event, h.fn, h.opts);
    this._docHandlers = [];
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; font-family:var(--font-sans,"Inter",sans-serif); color:var(--text-primary,#e0e0e0); }
        .p { display:grid; grid-template-columns:1fr 1fr; gap:12px; padding:12px; }
        :host(.tier-arcade) .p { border:2px solid var(--status-warning,#ffaa00); border-radius:6px; }
        .olbl { display:none; grid-column:1/-1; text-align:center; font-size:.75rem; font-weight:700;
                 color:var(--status-warning,#ffaa00); text-transform:uppercase; letter-spacing:.1em; }
        :host(.tier-arcade) .olbl { display:block; }
        .sl { font-size:.65rem; text-transform:uppercase; color:var(--text-dim,#555566); margin-bottom:8px; letter-spacing:.08em; }
        .ts { display:flex; flex-direction:column; gap:8px; }
        .tr { display:flex; align-items:center; gap:8px; }
        .tt { flex:1; height:24px; background:var(--bg-input,#1a1a24); border-radius:12px; position:relative; cursor:pointer; }
        .tf { position:absolute; left:0; top:0; bottom:0; background:var(--status-info,#00aaff); border-radius:12px; transition:width .1s; pointer-events:none; }
        .th { position:absolute; top:2px; width:20px; height:20px; background:var(--status-info,#00aaff); border-radius:50%; cursor:grab; transform:translateX(-50%); transition:background .1s; }
        .th:hover { background:var(--text-bright,#fff); }
        .th.drag { cursor:grabbing; background:var(--status-nominal,#00ff88); }
        .tp { font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.9rem; min-width:3.5em; text-align:right; }
        .ro { font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.75rem; color:var(--text-secondary,#888899); }
        .ro strong { color:var(--text-primary,#e0e0e0); }
        .gv { font-size:.85rem; font-weight:600; }
        .gv.c1 { color:var(--status-nominal,#00ff88); } .gv.c2 { color:var(--status-info,#00aaff); }
        .gv.c3 { color:var(--status-warning,#ffaa00); } .gv.c4 { color:var(--status-critical,#ff4444); }
        .hs { display:flex; flex-direction:column; gap:8px; }
        .hg { display:grid; grid-template-columns:auto 1fr; gap:4px 8px; align-items:center;
               font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.8rem; }
        .hg .al { font-size:.65rem; text-transform:uppercase; color:var(--text-dim,#555566); }
        .hg input { width:100%; padding:4px 6px; background:var(--bg-primary,#0a0a0f); border:1px solid var(--border-default,#2a2a3a);
                     border-radius:4px; color:var(--text-primary,#e0e0e0); font-family:inherit; font-size:.8rem; text-align:right; box-sizing:border-box; }
        .hg input:focus { outline:none; border-color:var(--status-info,#00aaff); }
        .cw { display:flex; justify-content:center; margin-top:4px; }
        .cc { width:min(80px, 100%); aspect-ratio:1; border-radius:50%; background:var(--bg-input,#1a1a24); border:2px solid var(--border-default,#2a2a3a); position:relative; }
        .cl { position:absolute; font-size:.55rem; color:var(--text-dim,#555566); }
        .cl.n{top:2px;left:50%;transform:translateX(-50%)} .cl.s{bottom:2px;left:50%;transform:translateX(-50%)}
        .cl.e{right:2px;top:50%;transform:translateY(-50%)} .cl.w{left:2px;top:50%;transform:translateY(-50%)}
        .cn { position:absolute; top:50%; left:50%; width:3px; height:32px;
              background:linear-gradient(to top,var(--status-critical,#ff4444) 50%,var(--status-info,#00aaff) 50%);
              border-radius:1.5px; transform-origin:center bottom; transform:translate(-50%,-100%) rotate(0deg); transition:transform .2s; }
        .cd { position:absolute; top:50%; left:50%; width:8px; height:8px; background:var(--text-primary,#e0e0e0); border-radius:50%; transform:translate(-50%,-50%); }
        .ab { margin-top:6px; padding:6px 10px; background:var(--bg-input,#1a1a24); border:1px solid var(--border-default,#2a2a3a);
              border-radius:4px; color:var(--text-primary,#e0e0e0); font-size:.7rem; cursor:pointer; text-transform:uppercase; }
        .ab:hover { background:var(--bg-hover,#22222e); border-color:var(--status-info,#00aaff); }
        .vs { grid-column:1/-1; display:flex; justify-content:space-between; padding:8px 12px;
              background:var(--bg-input,#1a1a24); border-radius:4px; font-family:var(--font-mono,"JetBrains Mono",monospace);
              font-size:.75rem; color:var(--text-secondary,#888899); }
        .vs strong { color:var(--text-primary,#e0e0e0); }
        .rh { display:none; grid-column:1/-1; text-align:center; font-size:.6rem; color:var(--text-dim,#555566); padding-top:2px; }
        :host(.tier-raw) .rh { display:block; }
        :host(.tier-arcade) .hc { display:none; }
        .hro { display:none; }
        :host(.tier-arcade) .hro { display:block; font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.8rem; color:var(--text-secondary,#888899); padding:4px 0; }
        .all-stop { grid-column:1/-1; padding:10px; background:var(--status-critical,#ff4444); border:none; border-radius:4px;
                    color:#fff; font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.85rem; font-weight:700;
                    text-transform:uppercase; letter-spacing:.1em; cursor:pointer; }
        .all-stop:hover { background:#ff2222; }
        .all-stop:active { background:#cc0000; }
        /* Manual-tier coordinate navigation section — visible only in MANUAL tier */
        .manual-only { display:none; grid-column:1/-1; }
        :host(.tier-manual) .manual-only { display:block; }
        .mo-title { font-size:.65rem; text-transform:uppercase; color:var(--status-warning,#ffaa00); letter-spacing:.1em;
                    margin-bottom:8px; font-weight:700; }
        .mo-grid { display:grid; grid-template-columns:auto 1fr; gap:4px 8px; align-items:center;
                   font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.8rem; }
        .mo-grid .al { font-size:.65rem; text-transform:uppercase; color:var(--text-dim,#555566); }
        .mo-grid input { width:100%; padding:4px 6px; background:var(--bg-primary,#0a0a0f);
                         border:1px solid var(--border-default,#2a2a3a); border-radius:4px;
                         color:var(--text-primary,#e0e0e0); font-family:inherit; font-size:.8rem;
                         text-align:right; box-sizing:border-box; }
        .mo-grid input:focus { outline:none; border-color:var(--status-warning,#ffaa00); }
        .mo-go { margin-top:6px; padding:6px 10px; width:100%; background:var(--bg-input,#1a1a24);
                 border:1px solid var(--status-warning,#ffaa00); border-radius:4px;
                 color:var(--status-warning,#ffaa00); font-family:var(--font-mono,"JetBrains Mono",monospace);
                 font-size:.75rem; font-weight:700; cursor:pointer; text-transform:uppercase; letter-spacing:.1em; }
        .mo-go:hover { background:var(--status-warning,#ffaa00); color:#000; }
        .mo-pos { margin-top:6px; padding:6px 8px; background:var(--bg-input,#1a1a24); border-radius:4px;
                  font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.7rem;
                  color:var(--text-dim,#555566); }
        .mo-pos strong { color:var(--text-secondary,#888899); }
      </style>
      <div class="p">
        <div class="olbl">Manual Override</div>
        <div class="ts">
          <div class="sl">Throttle</div>
          <div class="tr">
            <div class="tt" id="tt"><div class="tf" id="tf"></div><div class="th" id="th"></div></div>
            <span class="tp" id="tp">0%</span>
          </div>
          <div class="ro">G: <span class="gv" id="gv">0.0</span>g</div>
          <div class="ro">Thrust: <strong id="tn">0</strong> N</div>
        </div>
        <div class="hs">
          <div class="sl">Heading</div>
          <div class="hc" id="hc">
            <div class="hg">
              <span class="al">Yaw</span><input type="number" id="yi" min="0" max="360" step="0.1" value="0"/>
              <span class="al">Pitch</span><input type="number" id="pi" min="-90" max="90" step="0.1" value="0"/>
              <span class="al">Roll</span><input type="number" id="ri" min="-180" max="180" step="0.1" value="0"/>
            </div>
            <button class="ab" id="ab">Apply Heading</button>
          </div>
          <div class="hro" id="hro">
            P: <span id="rp">+0.0</span> | Y: <span id="ry">000.0</span> | R: <span id="rr">+0.0</span>
            <div style="font-size:.6rem;color:var(--text-dim,#555566);margin-top:4px">Autopilot controlling heading</div>
          </div>
          <div class="cw"><div class="cc">
            <span class="cl n">000</span><span class="cl e">090</span><span class="cl s">180</span><span class="cl w">270</span>
            <div class="cn" id="cn"></div><div class="cd"></div>
          </div></div>
        </div>
        <div class="vs">
          <span>Vel: <strong id="vm">0.0</strong> m/s</span>
          <span>Hdg: <strong id="vh">---</strong></span>
          <span>Accel: <strong id="ag">0.0</strong>g</span>
        </div>
        <button class="all-stop" id="allstop" title="Kill all velocity (X)">ALL STOP</button>
        <div class="manual-only" id="manual-nav">
          <div class="mo-title">Navigate to Coordinates</div>
          <div class="mo-grid">
            <span class="al">X (m)</span><input type="number" id="mx" step="100" value="0"/>
            <span class="al">Y (m)</span><input type="number" id="my" step="100" value="0"/>
            <span class="al">Z (m)</span><input type="number" id="mz" step="100" value="0"/>
          </div>
          <button class="mo-go" id="mogo">GO</button>
          <div class="mo-pos">Current: X <strong id="cpx">0</strong> Y <strong id="cpy">0</strong> Z <strong id="cpz">0</strong></div>
        </div>
        <div class="rh">WASD/QE for RCS fine control</div>
      </div>`;
  }

  // ── State ───────────────────────────────────────────────────────────
  _updateFromState() {
    const nav = stateManager.getNavigation();
    const ship = stateManager.getShipState();
    const prop = ship?.systems?.propulsion || {};
    // Throttle
    const thr = prop.throttle ?? nav.thrust ?? 0;
    this._throttle = thr;
    if (!this._isDragging && !this._pendingThrottle) this._setThrottleVis(thr);
    // G-force
    this._currentG = prop.thrust_g || 0;
    const gEl = this.shadowRoot.getElementById("gv");
    if (gEl) {
      gEl.textContent = this._currentG.toFixed(1);
      gEl.className = "gv " + (this._currentG < 0.3 ? "c1" : this._currentG < 1 ? "c2" : this._currentG < 3 ? "c3" : "c4");
    }
    // Thrust Newtons
    this._maxForceN = prop.max_thrust_force || 0;
    const fN = this._maxForceN * thr;
    const tn = this.shadowRoot.getElementById("tn");
    if (tn) tn.textContent = fN > 1000 ? `${(fN/1000).toFixed(1)}k` : Math.round(fN).toLocaleString();
    // Heading
    const h = nav.heading || {};
    this._pitch = h.pitch || 0; this._yaw = h.yaw || 0; this._roll = h.roll || 0;
    this._updateHeading();
    // Velocity
    this._velocity = nav.velocity || [0, 0, 0];
    this._updateVelStrip();
    // Current position (manual-tier coordinate display)
    const pos = ship?.position;
    if (pos) {
      const cpx = this.shadowRoot.getElementById("cpx");
      const cpy = this.shadowRoot.getElementById("cpy");
      const cpz = this.shadowRoot.getElementById("cpz");
      const fmt = (v) => Math.abs(v) > 1000 ? `${(v / 1000).toFixed(1)}k` : Math.round(v).toString();
      if (cpx) cpx.textContent = fmt(pos.x ?? pos[0] ?? 0);
      if (cpy) cpy.textContent = fmt(pos.y ?? pos[1] ?? 0);
      if (cpz) cpz.textContent = fmt(pos.z ?? pos[2] ?? 0);
    }
  }

  _setThrottleVis(v) {
    const pct = Math.max(0, Math.min(1, v)) * 100;
    const f = this.shadowRoot.getElementById("tf");
    const h = this.shadowRoot.getElementById("th");
    const l = this.shadowRoot.getElementById("tp");
    if (f) f.style.width = `${pct}%`;
    if (h) h.style.left = `${pct}%`;
    if (l) l.textContent = `${Math.round(pct)}%`;
  }

  _updateHeading() {
    const cn = this.shadowRoot.getElementById("cn");
    if (cn) cn.style.transform = `translate(-50%,-100%) rotate(${this._yaw}deg)`;
    // Read-only (ARCADE)
    const rp = this.shadowRoot.getElementById("rp");
    const ry = this.shadowRoot.getElementById("ry");
    const rr = this.shadowRoot.getElementById("rr");
    const sign = (v) => (v >= 0 ? "+" : "") + v.toFixed(1);
    if (rp) rp.textContent = sign(this._pitch);
    if (ry) ry.textContent = this._yaw.toFixed(1).padStart(5, "0");
    if (rr) rr.textContent = sign(this._roll);
    // Editable inputs (RAW) -- skip if focused
    const active = this.shadowRoot.activeElement;
    const pi = this.shadowRoot.getElementById("pi");
    const yi = this.shadowRoot.getElementById("yi");
    const ri = this.shadowRoot.getElementById("ri");
    if (pi && active !== pi) pi.value = this._pitch.toFixed(1);
    if (yi && active !== yi) yi.value = this._yaw.toFixed(1);
    if (ri && active !== ri) ri.value = this._roll.toFixed(1);
  }

  _updateVelStrip() {
    const [vx, vy, vz] = this._velocity;
    const mag = Math.sqrt(vx*vx + vy*vy + vz*vz);
    const vm = this.shadowRoot.getElementById("vm");
    if (vm) vm.textContent = mag.toFixed(1);
    const vh = this.shadowRoot.getElementById("vh");
    if (vh) vh.textContent = mag > 0.1 ? `${((Math.atan2(vx,vz)*180/Math.PI+360)%360).toFixed(0).padStart(3,"0")}` : "---";
    const ag = this.shadowRoot.getElementById("ag");
    if (ag) ag.textContent = this._currentG.toFixed(1);
  }

  // ── Interaction ─────────────────────────────────────────────────────
  _setupInteraction() {
    const track = this.shadowRoot.getElementById("tt");
    const handle = this.shadowRoot.getElementById("th");
    const valFromEvt = (e) => {
      const r = track.getBoundingClientRect();
      const cx = e.touches ? e.touches[0].clientX : e.clientX;
      return Math.max(0, Math.min(1, (cx - r.left) / r.width));
    };
    const start = (e) => { e.preventDefault(); this._isDragging = true; handle.classList.add("drag"); this._setThrottleVis(valFromEvt(e)); };
    const move = (e) => { if (!this._isDragging) return; e.preventDefault(); this._setThrottleVis(valFromEvt(e)); };
    const end = () => {
      if (!this._isDragging) return;
      this._isDragging = false; handle.classList.remove("drag");
      this._sendThrottle((parseFloat(handle.style.left) || 0) / 100);
    };
    track.addEventListener("mousedown", start);
    track.addEventListener("touchstart", start, { passive: false });
    const addDoc = (ev, fn, opts) => { document.addEventListener(ev, fn, opts); this._docHandlers.push({event:ev,fn,opts}); };
    addDoc("mousemove", move); addDoc("touchmove", move, {passive:false});
    addDoc("mouseup", end); addDoc("touchend", end);
    // All Stop
    const allstop = this.shadowRoot.getElementById("allstop");
    if (allstop) allstop.addEventListener("click", () => this._allStop());
    // Heading apply
    const ab = this.shadowRoot.getElementById("ab");
    if (ab) ab.addEventListener("click", () => this._applyHeading());
    ["pi","yi","ri"].forEach(id => {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.addEventListener("keydown", (e) => { if (e.key === "Enter") this._applyHeading(); });
    });
    // Manual-tier coordinate navigation
    const mogo = this.shadowRoot.getElementById("mogo");
    if (mogo) mogo.addEventListener("click", () => this._goToCoords());
    ["mx","my","mz"].forEach(id => {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.addEventListener("keydown", (e) => { if (e.key === "Enter") this._goToCoords(); });
    });
  }

  // ── Commands (same as throttle-control.js / heading-control.js) ────
  async _sendThrottle(value) {
    this._pendingThrottle = true;
    try {
      const r = await wsClient.sendShipCommand("set_thrust", { thrust: value });
      if (r?.ok === false || r?.error) { this._setThrottleVis(this._throttle); }
      else if (r?.ok === true) { const res = r.response || r; if (res?.throttle !== undefined) { this._throttle = res.throttle; this._setThrottleVis(this._throttle); } }
    } catch { this._setThrottleVis(this._throttle); }
    finally { this._pendingThrottle = false; }
  }

  async _applyHeading() {
    const pitch = Math.max(-90, Math.min(90, parseFloat(this.shadowRoot.getElementById("pi")?.value) || 0));
    const yaw = ((parseFloat(this.shadowRoot.getElementById("yi")?.value) || 0) % 360 + 360) % 360;
    const roll = Math.max(-180, Math.min(180, parseFloat(this.shadowRoot.getElementById("ri")?.value) || 0));
    try {
      const r = await wsClient.sendShipCommand("set_orientation", { pitch, yaw, roll });
      if (r?.ok === true) {
        const t = (r.response || r)?.target;
        if (t) { this._pitch = t.pitch ?? this._pitch; this._yaw = t.yaw ?? this._yaw; this._roll = t.roll ?? this._roll; this._updateHeading(); }
      } else if (r?.ok === false || r?.error) {
        this._showMsg(`Heading error: ${r.error || r.message || "Unknown"}`, "error");
      }
    } catch (err) { this._showMsg(`Heading failed: ${err.message}`, "error"); }
  }

  async _allStop() {
    try {
      const r = await wsClient.sendShipCommand("autopilot", { program: "all_stop", g_level: 1.0 });
      if (r?.ok) { this._showMsg("All stop engaged", "success"); }
      else { this._showMsg(r?.error || "All stop failed", "error"); }
    } catch (err) { this._showMsg(`All stop failed: ${err.message}`, "error"); }
  }

  /** Send set_course command with raw X/Y/Z coordinates (MANUAL tier) */
  async _goToCoords() {
    const x = parseFloat(this.shadowRoot.getElementById("mx")?.value) || 0;
    const y = parseFloat(this.shadowRoot.getElementById("my")?.value) || 0;
    const z = parseFloat(this.shadowRoot.getElementById("mz")?.value) || 0;
    try {
      const r = await wsClient.sendShipCommand("set_course", {
        x, y, z, stop: true, tolerance: 100, max_thrust: 1.0
      });
      if (r?.ok) { this._showMsg(`Course set: [${x}, ${y}, ${z}]`, "success"); }
      else { this._showMsg(r?.error || "Set course failed", "error"); }
    } catch (err) { this._showMsg(`Set course failed: ${err.message}`, "error"); }
  }

  _showMsg(text, type) { const el = document.getElementById("system-messages"); if (el?.show) el.show({type,text}); }

  // ── Tier ────────────────────────────────────────────────────────────
  _applyTier() {
    this.classList.remove("tier-raw", "tier-arcade", "tier-cpu-assist", "tier-manual");
    this.classList.add(`tier-${this._tier}`);
  }
}

customElements.define("manual-flight-panel", ManualFlightPanel);
export { ManualFlightPanel };
