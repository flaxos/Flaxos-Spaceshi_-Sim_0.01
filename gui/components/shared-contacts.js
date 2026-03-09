/**
 * Tactical Data Link - Shared Contacts
 * Share sensor contacts with the fleet and mark hostiles.
 * Sends share_contact commands via wsClient.sendShipCommand().
 */
import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

class SharedContacts extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._sharedIds = new Set();
    this._hostileIds = new Set();
  }

  connectedCallback() {
    this._render();
    this._setupEvents();
    this._unsubscribe = stateManager.subscribe("*", () => this._updateDisplay());
  }

  disconnectedCallback() {
    if (this._unsubscribe) { this._unsubscribe(); this._unsubscribe = null; }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:flex; flex-direction:column; font-family:var(--font-mono,"JetBrains Mono",monospace);
          font-size:0.75rem; color:var(--text-primary,#e0e0e0); background:var(--bg-panel,#12121a); height:100%; }
        .header { display:flex; justify-content:space-between; align-items:center; padding:8px 12px;
          border-bottom:1px solid var(--border-default,#2a2a3a); background:rgba(0,0,0,0.2); }
        .header-title { font-weight:600; letter-spacing:0.05em; }
        .link-indicator { width:8px; height:8px; border-radius:50%; background:var(--status-nominal,#00ff88); }
        .link-indicator.inactive { background:var(--text-dim,#666680); }
        table { width:100%; border-collapse:collapse; }
        th { text-align:left; padding:6px 8px; color:var(--text-dim,#666680);
          border-bottom:1px solid var(--border-default,#2a2a3a); font-weight:400;
          text-transform:uppercase; font-size:0.65rem; letter-spacing:0.08em; }
        td { padding:5px 8px; border-bottom:1px solid var(--border-default,#2a2a3a); }
        tr.shared td { background:rgba(68,136,255,0.08); }
        tr.hostile td { background:rgba(255,68,68,0.1); }
        .contacts-body { flex:1; overflow-y:auto; }
        .empty { padding:24px; text-align:center; color:var(--text-dim,#666680); }
        .share-btn { background:var(--bg-input,#1a1a2e); color:var(--status-info,#4488ff);
          border:1px solid var(--status-info,#4488ff); padding:2px 8px; font-family:inherit;
          font-size:0.65rem; cursor:pointer; letter-spacing:0.05em; }
        .share-btn:hover { background:rgba(68,136,255,0.15); }
        .share-btn.active { background:var(--status-info,#4488ff); color:var(--bg-panel,#12121a); }
        input[type="checkbox"] { accent-color:var(--status-critical,#ff4444); cursor:pointer; }
        .footer { padding:6px 12px; border-top:1px solid var(--border-default,#2a2a3a);
          color:var(--text-secondary,#a0a0b0); font-size:0.65rem; display:flex; justify-content:space-between; }
      </style>
      <div class="header">
        <span class="header-title">TACTICAL DATA LINK</span>
        <span class="link-indicator" id="link-indicator" title="Link status"></span>
      </div>
      <div class="contacts-body" id="contacts-body">
        <table>
          <thead><tr><th>ID</th><th>RANGE</th><th>BRG</th><th>SHARE</th><th>HOSTILE</th></tr></thead>
          <tbody id="contact-rows"></tbody>
        </table>
      </div>
      <div class="footer">
        <span id="contact-count">0 contacts</span>
        <span id="shared-count">0 shared</span>
      </div>`;
  }

  _setupEvents() {
    this.shadowRoot.getElementById("contacts-body").addEventListener("click", (e) => {
      const btn = e.target.closest(".share-btn");
      if (btn) { this._toggleShare(btn.dataset.id); return; }
      const cb = e.target.closest("input[type='checkbox']");
      if (cb) this._toggleHostile(cb.dataset.id, cb.checked);
    });
  }

  _findContact(contactId) {
    const contacts = stateManager.getContacts();
    return contacts?.find(c => (c.contact_id || c.id) === contactId);
  }

  async _toggleShare(contactId) {
    const contact = this._findContact(contactId);
    if (!contact) return;
    if (this._sharedIds.has(contactId)) {
      this._sharedIds.delete(contactId);
    } else {
      this._sharedIds.add(contactId);
      try {
        await wsClient.sendShipCommand("share_contact", {
          contact, hostile: this._hostileIds.has(contactId),
        });
      } catch (err) {
        console.error("Failed to share contact:", err);
        this._sharedIds.delete(contactId);
      }
    }
    this._updateDisplay();
  }

  async _toggleHostile(contactId, hostile) {
    hostile ? this._hostileIds.add(contactId) : this._hostileIds.delete(contactId);
    // Re-share with updated hostile flag if already shared
    if (this._sharedIds.has(contactId)) {
      const contact = this._findContact(contactId);
      if (contact) {
        try {
          await wsClient.sendShipCommand("share_contact", { contact, hostile });
        } catch (err) { console.error("Failed to update hostile flag:", err); }
      }
    }
    this._updateDisplay();
  }

  _formatRange(range) {
    if (range >= 1000) return `${(range / 1000).toFixed(1)}Mm`;
    if (range >= 1) return `${range.toFixed(1)}km`;
    return `${(range * 1000).toFixed(0)}m`;
  }

  _updateDisplay() {
    const contacts = stateManager.getContacts();
    const connected = wsClient.status === "connected";
    const indicator = this.shadowRoot.getElementById("link-indicator");
    indicator.classList.toggle("inactive", !connected);
    indicator.title = connected ? "Link active" : "Link inactive";

    const tbody = this.shadowRoot.getElementById("contact-rows");
    if (!contacts || contacts.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty">No contacts detected</td></tr>`;
    } else {
      tbody.innerHTML = contacts.map(c => {
        const id = c.contact_id || c.id || "???";
        const range = c.range ?? c.distance ?? 0;
        const bearing = c.bearing ?? "---";
        const shared = this._sharedIds.has(id);
        const hostile = this._hostileIds.has(id);
        const cls = hostile ? "hostile" : shared ? "shared" : "";
        return `<tr class="${cls}">
          <td>${id}</td><td>${this._formatRange(range)}</td><td>${bearing}</td>
          <td><button class="share-btn ${shared ? "active" : ""}" data-id="${id}">${shared ? "SHARED" : "SHARE"}</button></td>
          <td><input type="checkbox" data-id="${id}" ${hostile ? "checked" : ""}></td></tr>`;
      }).join("");
    }
    this.shadowRoot.getElementById("contact-count").textContent = `${contacts?.length || 0} contacts`;
    this.shadowRoot.getElementById("shared-count").textContent = `${this._sharedIds.size} shared`;
  }
}

customElements.define("shared-contacts", SharedContacts);
