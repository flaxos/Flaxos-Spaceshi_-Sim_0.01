/**
 * Panel Container Component
 * Consistent header styling with optional collapse/expand
 * Supports priority levels, domain color accents, and disabled state with reason overlay
 */

const DOMAIN_COLORS = {
  nav:     "--domain-nav",
  sensor:  "--domain-sensor",
  weapons: "--domain-weapons",
  power:   "--domain-power",
  comms:   "--domain-comms",
  helm:    "--domain-helm",
};

class FlaxosPanel extends HTMLElement {
  static get observedAttributes() {
    return ["title", "collapsible", "collapsed", "minimizable", "priority", "domain", "disabled-reason"];
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._collapsed = false;
  }

  connectedCallback() {
    this.render();
    this._updateCollapsedState();
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (oldValue === newValue) return;

    if (name === "collapsed") {
      this._collapsed = newValue !== null && newValue !== "false";
      this._updateCollapsedState();
    } else {
      this.render();
    }
  }

  get title() {
    return this.getAttribute("title") || "";
  }

  get collapsible() {
    return this.hasAttribute("collapsible");
  }

  get minimizable() {
    return this.hasAttribute("minimizable");
  }

  get collapsed() {
    return this._collapsed;
  }

  set collapsed(value) {
    this._collapsed = !!value;
    if (value) {
      this.setAttribute("collapsed", "");
    } else {
      this.removeAttribute("collapsed");
    }
    this._updateCollapsedState();
  }

  get priority() {
    const val = this.getAttribute("priority");
    if (val === "primary" || val === "tertiary") return val;
    return "secondary";
  }

  get domain() {
    return this.getAttribute("domain") || null;
  }

  get disabledReason() {
    return this.getAttribute("disabled-reason") || null;
  }

  toggle() {
    this.collapsed = !this.collapsed;
  }

  /**
   * Build the domain color CSS variable assignment.
   * When a valid domain is set, --panel-domain-color resolves to the
   * corresponding --domain-* variable so other styles can reference it.
   */
  _getDomainColorRule() {
    const d = this.domain;
    if (d && DOMAIN_COLORS[d]) {
      return `--panel-domain-color: var(${DOMAIN_COLORS[d]});`;
    }
    return `--panel-domain-color: transparent;`;
  }

  render() {
    const domainRule = this._getDomainColorRule();
    const isDisabled = this.disabledReason !== null;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          background: var(--bg-panel, #12121a);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: var(--radius-md, 8px);
          overflow: hidden;
          position: relative;
          ${domainRule}
        }

        /* --- Priority: primary --- */
        :host([priority="primary"]) {
          background: var(--bg-panel-raised, #161622);
          border-color: var(--border-active, #3a3a4a);
          border-left: 3px solid var(--panel-domain-color, var(--border-active, #3a3a4a));
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
        }

        /* --- Priority: tertiary --- */
        :host([priority="tertiary"]) {
          border-color: var(--border-subtle, #1e1e2e);
          opacity: 0.85;
        }

        /* --- Disabled state --- */
        :host([disabled-reason]) {
          opacity: 0.4;
        }

        .header::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 2px;
          background: var(--panel-domain-color, transparent);
          opacity: 0.6;
        }

        .header {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 16px;
          background: linear-gradient(
            135deg,
            rgba(255, 255, 255, 0.035) 0%,
            rgba(255, 255, 255, 0.01) 100%
          );
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
          min-height: 36px;
          user-select: none;
        }

        .title {
          font-size: 0.8rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
        }

        :host([domain]) .title {
          color: color-mix(in srgb, var(--panel-domain-color) 40%, var(--text-secondary, #888899));
        }

        .actions {
          display: flex;
          gap: 4px;
        }

        .action-btn {
          background: transparent;
          border: none;
          color: var(--text-dim, #555566);
          cursor: pointer;
          padding: 4px 8px;
          font-size: 0.75rem;
          border-radius: 4px;
          transition: all 0.1s ease;
          min-height: auto;
        }

        .action-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-primary, #e0e0e0);
        }

        .content {
          flex: 1;
          overflow-y: auto;
          position: relative;
        }

        .content.collapsed {
          display: none;
        }

        /* Block interaction when panel is disabled */
        .content.disabled {
          pointer-events: none;
        }

        /* Damaged panel states */
        :host([data-health="impaired"]) .content {
          animation: damage-flicker 4s ease-in-out infinite;
        }
        :host([data-health="critical"]) .content {
          animation: damage-flicker 1.5s ease-in-out infinite;
          filter: contrast(0.85) brightness(0.9);
        }

        @keyframes damage-flicker {
          0%, 94%, 96%, 98%, 100% { opacity: 1; }
          95%, 97%                 { opacity: 0.65; }
        }

        .collapse-icon {
          display: inline-block;
          transition: transform 0.2s ease;
        }

        .collapse-icon.collapsed {
          transform: rotate(-90deg);
        }

        ::slotted(*) {
          padding: 16px;
        }

        /* Disabled reason overlay — sits inside content area so title bar stays visible */
        .disabled-overlay {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 16px;
          background:
            repeating-linear-gradient(
              -45deg,
              transparent,
              transparent 3px,
              rgba(0, 0, 0, 0.08) 3px,
              rgba(0, 0, 0, 0.08) 4px
            ),
            rgba(6, 6, 9, 0.65);
          z-index: 5;
          pointer-events: none;
        }
        .disabled-overlay .reason-text {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-dim, #555570);
          text-align: center;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          line-height: 1.4;
        }
      </style>

      <div class="header" part="header">
        <span class="title" part="title">${this.title}</span>
        <div class="actions" part="actions">
          <slot name="actions"></slot>
          ${this.collapsible ? `
            <button class="action-btn" id="toggle-btn" title="Toggle">
              <span class="collapse-icon" id="collapse-icon">▼</span>
            </button>
          ` : ""}
          ${this.minimizable ? `
            <button class="action-btn" id="minimize-btn" title="Minimize">─</button>
          ` : ""}
        </div>
      </div>
      <div class="content${isDisabled ? " disabled" : ""}" id="content" part="content">
        <slot></slot>
        ${isDisabled ? `
          <div class="disabled-overlay">
            <span class="reason-text">${this._escapeHtml(this.disabledReason)}</span>
          </div>
        ` : ""}
      </div>
    `;

    this._bindEvents();
  }

  /** Escape HTML entities to prevent XSS in disabled-reason text */
  _escapeHtml(str) {
    if (!str) return "";
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
    return str.replace(/[&<>"']/g, (c) => map[c]);
  }

  _bindEvents() {
    const toggleBtn = this.shadowRoot.getElementById("toggle-btn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => this.toggle());
    }

    const minimizeBtn = this.shadowRoot.getElementById("minimize-btn");
    if (minimizeBtn) {
      minimizeBtn.addEventListener("click", () => {
        this.dispatchEvent(new CustomEvent("minimize", { bubbles: true }));
      });
    }

    // Double-click header to toggle
    if (this.collapsible) {
      const header = this.shadowRoot.querySelector(".header");
      header.addEventListener("dblclick", () => this.toggle());
    }
  }

  _updateCollapsedState() {
    const content = this.shadowRoot.getElementById("content");
    const icon = this.shadowRoot.getElementById("collapse-icon");

    if (content) {
      content.classList.toggle("collapsed", this._collapsed);
    }
    if (icon) {
      icon.classList.toggle("collapsed", this._collapsed);
    }
  }
}

customElements.define("flaxos-panel", FlaxosPanel);
export { FlaxosPanel };
