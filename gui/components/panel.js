/**
 * Panel Container Component
 * Consistent header styling with optional collapse/expand
 */

class FlaxosPanel extends HTMLElement {
  static get observedAttributes() {
    return ["title", "collapsible", "collapsed", "minimizable"];
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

  toggle() {
    this.collapsed = !this.collapsed;
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          background: var(--bg-panel, #12121a);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: var(--radius-md, 8px);
          overflow: hidden;
        }

        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 16px;
          background: rgba(255, 255, 255, 0.02);
          border-bottom: 1px solid var(--border-default, #2a2a3a);
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
        }

        .content.collapsed {
          display: none;
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
      <div class="content" id="content" part="content">
        <slot></slot>
      </div>
    `;

    this._bindEvents();
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
