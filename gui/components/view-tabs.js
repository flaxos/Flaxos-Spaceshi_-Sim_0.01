/**
 * View Tabs Component
 * Tab bar for switching between Helm, Tactical, Engineering, and Mission views.
 * Keyboard shortcuts: 1=Helm, 2=Tactical, 3=Engineering, 4=Mission
 */

class ViewTabs extends HTMLElement {
  static get observedAttributes() {
    return ["active"];
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._activeView = "helm";
    this._keyHandler = null;
  }

  connectedCallback() {
    this.render();
    this._setupKeyboardShortcuts();
  }

  disconnectedCallback() {
    if (this._keyHandler) {
      document.removeEventListener("keydown", this._keyHandler);
      this._keyHandler = null;
    }
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (name === "active" && newValue && newValue !== oldValue) {
      this._activeView = newValue;
      this._updateActiveTab();
    }
  }

  get activeView() {
    return this._activeView;
  }

  set activeView(value) {
    if (this._activeView === value) return;
    this._activeView = value;
    this.setAttribute("active", value);
    this._updateActiveTab();
    this._emitChange();
  }

  render() {
    const tabs = [
      { id: "helm", label: "HELM", shortcut: "1", icon: "H" },
      { id: "tactical", label: "TACTICAL", shortcut: "2", icon: "T" },
      { id: "engineering", label: "ENGINEERING", shortcut: "3", icon: "E" },
      { id: "mission", label: "MISSION", shortcut: "4", icon: "M" },
    ];

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          background: var(--bg-panel, #12121a);
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          user-select: none;
        }

        .tab-bar {
          display: flex;
          gap: 2px;
          padding: 4px 8px;
          align-items: stretch;
        }

        .tab {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 10px 16px;
          background: transparent;
          border: 1px solid transparent;
          border-radius: 6px 6px 0 0;
          color: var(--text-secondary, #888899);
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
          cursor: pointer;
          transition: all 0.15s ease;
          min-height: 40px;
          position: relative;
        }

        .tab:hover {
          background: var(--bg-hover, #22222e);
          color: var(--text-primary, #e0e0e0);
        }

        .tab.active {
          background: var(--bg-primary, #0a0a0f);
          border-color: var(--border-default, #2a2a3a);
          border-bottom-color: var(--bg-primary, #0a0a0f);
          color: var(--text-bright, #ffffff);
        }

        .tab.active::after {
          content: "";
          position: absolute;
          bottom: -1px;
          left: 0;
          right: 0;
          height: 2px;
          background: var(--status-info, #00aaff);
        }

        .tab-shortcut {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          padding: 1px 5px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 3px;
          color: var(--text-dim, #555566);
        }

        .tab.active .tab-shortcut {
          background: rgba(0, 170, 255, 0.15);
          color: var(--status-info, #00aaff);
        }

        .tab-icon {
          display: none;
        }

        @media (max-width: 768px) {
          .tab-bar {
            padding: 2px 4px;
          }

          .tab {
            padding: 8px 4px;
            font-size: 0.65rem;
            letter-spacing: 0.5px;
            gap: 4px;
            flex-direction: column;
          }

          .tab-shortcut {
            display: none;
          }

          .tab-icon {
            display: block;
            font-size: 1rem;
            font-weight: 700;
          }

          .tab-label {
            font-size: 0.55rem;
          }
        }

        @media (max-width: 480px) {
          .tab-label {
            display: none;
          }

          .tab-icon {
            display: block;
            font-size: 1.1rem;
          }
        }
      </style>

      <nav class="tab-bar" role="tablist">
        ${tabs.map(tab => `
          <button
            class="tab ${tab.id === this._activeView ? "active" : ""}"
            role="tab"
            data-view="${tab.id}"
            aria-selected="${tab.id === this._activeView}"
            title="${tab.label} (${tab.shortcut})"
          >
            <span class="tab-icon">${tab.icon}</span>
            <span class="tab-label">${tab.label}</span>
            <span class="tab-shortcut">${tab.shortcut}</span>
          </button>
        `).join("")}
      </nav>
    `;

    // Bind click events
    this.shadowRoot.querySelectorAll(".tab").forEach(tab => {
      tab.addEventListener("click", () => {
        this.activeView = tab.dataset.view;
      });
    });
  }

  _setupKeyboardShortcuts() {
    const viewMap = { "1": "helm", "2": "tactical", "3": "engineering", "4": "mission" };

    this._keyHandler = (e) => {
      // Don't capture if user is typing in an input
      const tag = e.target.tagName.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      // Don't capture if inside a shadow DOM input
      if (e.composedPath().some(el => {
        const t = el.tagName?.toLowerCase();
        return t === "input" || t === "textarea" || t === "select";
      })) return;

      if (viewMap[e.key]) {
        e.preventDefault();
        this.activeView = viewMap[e.key];
      }
    };

    document.addEventListener("keydown", this._keyHandler);
  }

  _updateActiveTab() {
    const tabs = this.shadowRoot.querySelectorAll(".tab");
    tabs.forEach(tab => {
      const isActive = tab.dataset.view === this._activeView;
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-selected", isActive);
    });
  }

  _emitChange() {
    this.dispatchEvent(new CustomEvent("view-change", {
      detail: { view: this._activeView },
      bubbles: true,
      composed: true
    }));
  }
}

customElements.define("view-tabs", ViewTabs);
export { ViewTabs };
