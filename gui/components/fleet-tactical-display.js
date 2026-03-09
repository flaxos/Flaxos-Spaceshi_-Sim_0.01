/**
 * Fleet Tactical Display Component
 * Canvas-based multi-ship tactical overview showing fleet positions,
 * formation shape, and threat contacts. Polls fleet_tactical every 3s.
 */
import { wsClient } from "../js/ws-client.js";

const SCALE_OPTIONS = [5000, 10000, 50000, 100000, 500000]; // meters per screen radius

class FleetTacticalDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._canvas = null;
    this._ctx = null;
    this._canvasW = 0;
    this._canvasH = 0;
    this._scaleIndex = 2;
    this._pollInterval = null;
    this._fleetData = null;
    this._panX = 0; // pan offset in world-meters from fleet center of mass
    this._panY = 0;
    this._dragging = false;
    this._dragLastX = 0;
    this._dragLastY = 0;
  }

  connectedCallback() {
    this._buildDOM();
    this._canvas = this.shadowRoot.getElementById("cv");
    this._ctx = this._canvas.getContext("2d");
    new ResizeObserver(() => { this._resizeCanvas(); this._draw(); })
      .observe(this.shadowRoot.getElementById("wrap"));
    this._resizeCanvas();
    this._setupInteraction();
    this._poll();
    this._pollInterval = setInterval(() => this._poll(), 3000);
  }

  disconnectedCallback() {
    if (this._pollInterval) { clearInterval(this._pollInterval); this._pollInterval = null; }
  }

  async _poll() {
    try {
      this._fleetData = await wsClient.sendShipCommand("fleet_tactical", {});
    } catch (_) { /* connection not ready; keep stale data */ }
    this._draw();
  }

  _buildDOM() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:flex; flex-direction:column; height:100%;
          font-family:var(--font-mono,"JetBrains Mono",monospace); font-size:.75rem; }
        .bar { display:flex; align-items:center; gap:8px; padding:8px;
          border-bottom:1px solid var(--border-default,#2a2a3a); background:rgba(0,0,0,.2); }
        .bar .lbl { color:var(--text-dim,#666680); font-size:.65rem; text-transform:uppercase; }
        .bar button { background:transparent; border:1px solid var(--border-default,#2a2a3a);
          color:var(--text-primary,#e0e0e0); padding:4px 8px; border-radius:4px;
          cursor:pointer; font-size:.7rem; font-family:inherit; }
        .bar button:hover { background:rgba(255,255,255,.05); }
        .sv { color:var(--text-primary,#e0e0e0); min-width:60px; text-align:center; }
        .wrap { flex:1; position:relative; background:var(--bg-panel,#12121a); overflow:hidden; }
        canvas { width:100%; height:100%; display:block; cursor:grab; }
        canvas.dragging { cursor:grabbing; }
        .leg { position:absolute; bottom:8px; left:8px; background:rgba(0,0,0,.75);
          padding:8px 10px; border-radius:4px; border:1px solid var(--border-default,#2a2a3a);
          display:flex; gap:12px; font-size:.65rem; color:var(--text-dim,#666680); }
        .leg span { display:flex; align-items:center; gap:5px; }
        .lf { color:#00ff88; } .lh { color:#ff4444; } .ls { color:#ffdd44; }
      </style>
      <div class="bar">
        <span class="lbl">Scale</span>
        <button id="zo">-</button><span class="sv" id="sv"></span><button id="zi">+</button>
        <button id="rp" title="Reset pan to fleet center">C</button>
      </div>
      <div class="wrap" id="wrap"><canvas id="cv"></canvas>
        <div class="leg">
          <span class="lf">&#9650; Friendly</span>
          <span class="lh">&#9670; Hostile</span>
          <span class="ls">&#9650; Flagship</span>
        </div>
      </div>`;
    this._updateScaleLabel();
  }

  _resizeCanvas() {
    const r = this.shadowRoot.getElementById("wrap").getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this._canvas.width = r.width * dpr;
    this._canvas.height = r.height * dpr;
    this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._canvasW = r.width;
    this._canvasH = r.height;
  }

  _setupInteraction() {
    const sr = this.shadowRoot;
    sr.getElementById("zi").addEventListener("click", () => {
      if (this._scaleIndex > 0) { this._scaleIndex--; this._updateScaleLabel(); this._draw(); }
    });
    sr.getElementById("zo").addEventListener("click", () => {
      if (this._scaleIndex < SCALE_OPTIONS.length - 1) { this._scaleIndex++; this._updateScaleLabel(); this._draw(); }
    });
    sr.getElementById("rp").addEventListener("click", () => {
      this._panX = 0; this._panY = 0; this._draw();
    });
    this._canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      if (e.deltaY > 0 && this._scaleIndex < SCALE_OPTIONS.length - 1) this._scaleIndex++;
      else if (e.deltaY < 0 && this._scaleIndex > 0) this._scaleIndex--;
      this._updateScaleLabel(); this._draw();
    }, { passive: false });
    this._canvas.addEventListener("mousedown", (e) => {
      this._dragging = true; this._dragLastX = e.clientX; this._dragLastY = e.clientY;
      this._canvas.classList.add("dragging");
    });
    window.addEventListener("mousemove", (e) => {
      if (!this._dragging) return;
      const ppm = Math.min(this._canvasW, this._canvasH) / 2 / SCALE_OPTIONS[this._scaleIndex];
      this._panX -= (e.clientX - this._dragLastX) / ppm;
      this._panY += (e.clientY - this._dragLastY) / ppm;
      this._dragLastX = e.clientX; this._dragLastY = e.clientY;
      this._draw();
    });
    window.addEventListener("mouseup", () => {
      if (this._dragging) { this._dragging = false; this._canvas.classList.remove("dragging"); }
    });
  }

  _updateScaleLabel() {
    const s = SCALE_OPTIONS[this._scaleIndex];
    this.shadowRoot.getElementById("sv").textContent = s >= 1000 ? `${s / 1000} km` : `${s} m`;
  }

  /* ---- Drawing -------------------------------------------------------- */

  _draw() {
    const ctx = this._ctx;
    if (!ctx || !this._canvasW) return;
    const w = this._canvasW, h = this._canvasH;
    const cx = w / 2, cy = h / 2;
    const scale = SCALE_OPTIONS[this._scaleIndex];
    const ppm = Math.min(w, h) / 2 / scale;

    ctx.fillStyle = "#12121a";
    ctx.fillRect(0, 0, w, h);
    this._drawGrid(ctx, w, h, ppm, scale);

    const data = this._fleetData;
    if (!data) {
      ctx.fillStyle = "#666680"; ctx.font = "12px 'JetBrains Mono',monospace";
      ctx.textAlign = "center"; ctx.fillText("Awaiting fleet data...", cx, cy);
      ctx.textAlign = "start"; return;
    }

    const comX = (data.center_of_mass?.x ?? 0) + this._panX;
    const comZ = (data.center_of_mass?.z ?? 0) + this._panY;
    const toS = (wx, wz) => [cx + (wx - comX) * ppm, cy - (wz - comZ) * ppm];

    // Fleet center of mass crosshair
    const [ccx, ccy] = toS(data.center_of_mass?.x ?? 0, data.center_of_mass?.z ?? 0);
    ctx.strokeStyle = "#666680"; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(ccx - 12, ccy); ctx.lineTo(ccx + 12, ccy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(ccx, ccy - 12); ctx.lineTo(ccx, ccy + 12); ctx.stroke();
    ctx.setLineDash([]);

    // Formation overlay -- dotted lines connecting fleet ships
    const ships = data.ships || [];
    if (ships.length > 1) {
      ctx.strokeStyle = "#4488ff44"; ctx.lineWidth = 1; ctx.setLineDash([6, 4]);
      for (let i = 0; i < ships.length; i++) {
        for (let j = i + 1; j < ships.length; j++) {
          const [ax, ay] = toS(ships[i].position?.x ?? 0, ships[i].position?.z ?? 0);
          const [bx, by] = toS(ships[j].position?.x ?? 0, ships[j].position?.z ?? 0);
          ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
        }
      }
      ctx.setLineDash([]);
    }

    // Fleet ships -- green triangles, flagship gets gold outline and larger marker
    for (const ship of ships) {
      const [sx, sy] = toS(ship.position?.x ?? 0, ship.position?.z ?? 0);
      const flag = !!ship.flagship, sz = flag ? 10 : 7;
      ctx.fillStyle = "#00ff88";
      ctx.beginPath();
      ctx.moveTo(sx, sy - sz);
      ctx.lineTo(sx - sz * 0.7, sy + sz * 0.6);
      ctx.lineTo(sx + sz * 0.7, sy + sz * 0.6);
      ctx.closePath(); ctx.fill();
      if (flag) { ctx.strokeStyle = "#ffdd44"; ctx.lineWidth = 2; ctx.stroke(); }
      ctx.fillStyle = flag ? "#ffdd44" : "#00ff88";
      ctx.font = "10px 'JetBrains Mono',monospace"; ctx.textAlign = "left";
      ctx.fillText(ship.name || ship.id || "---", sx + sz + 4, sy + 4);
    }

    // Threats / contacts -- red diamonds
    const threats = data.threats || data.contacts || [];
    for (const t of threats) {
      const [tx, ty] = toS(t.position?.x ?? 0, t.position?.z ?? 0);
      const d = 6;
      ctx.fillStyle = "#ff4444"; ctx.beginPath();
      ctx.moveTo(tx, ty - d); ctx.lineTo(tx + d, ty);
      ctx.lineTo(tx, ty + d); ctx.lineTo(tx - d, ty);
      ctx.closePath(); ctx.fill();
      ctx.font = "10px 'JetBrains Mono',monospace"; ctx.textAlign = "left";
      ctx.fillText(t.name || t.id || "CONTACT", tx + d + 4, ty + 4);
    }

    this._drawScaleBar(ctx, w, h, scale, ppm);
  }

  _drawGrid(ctx, w, h, ppm, scale) {
    ctx.strokeStyle = "#1a1a2e"; ctx.lineWidth = 1;
    const sp = (scale / 4) * ppm;
    const ox = ((w / 2) + (-this._panX * ppm)) % sp;
    const oy = ((h / 2) + (this._panY * ppm)) % sp;
    for (let x = ox; x < w; x += sp) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
    for (let y = oy; y < h; y += sp) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
  }

  _drawScaleBar(ctx, w, h, scale, ppm) {
    const bw = scale / 4, bpx = bw * ppm, x0 = w - 20 - bpx, y0 = h - 40;
    ctx.strokeStyle = "#666680"; ctx.lineWidth = 1; ctx.beginPath();
    ctx.moveTo(x0, y0); ctx.lineTo(x0 + bpx, y0);
    ctx.moveTo(x0, y0 - 4); ctx.lineTo(x0, y0 + 4);
    ctx.moveTo(x0 + bpx, y0 - 4); ctx.lineTo(x0 + bpx, y0 + 4); ctx.stroke();
    ctx.fillStyle = "#666680"; ctx.font = "10px 'JetBrains Mono',monospace";
    ctx.textAlign = "center";
    ctx.fillText(bw >= 1000 ? `${bw / 1000} km` : `${bw} m`, x0 + bpx / 2, y0 - 8);
    ctx.textAlign = "start";
  }
}

customElements.define("fleet-tactical-display", FleetTacticalDisplay);
export { FleetTacticalDisplay };
