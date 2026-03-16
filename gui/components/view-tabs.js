/**
 * View Tabs Component
 * Tab bar for switching between station views.
 * Keyboard shortcuts: 1=Helm, 2=Tactical, 3=Ops, 4=Engineering, 5=Comms, 6=Science, 7=Fleet, 8=Mission, 9=Editor
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
    this._allowedViews = null; // null = all allowed, array = restricted
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
    // Reject switching to disallowed views
    if (this._allowedViews && !this._allowedViews.includes(value)) return;
    if (this._activeView === value) return;
    this._activeView = value;
    this.setAttribute("active", value);
    this._updateActiveTab();
    this._emitChange();
  }

  /**
   * Set which views are allowed. null = all allowed (captain/no station).
   * @param {string[]|null} views - Array of view ids, or null for unrestricted
   */
  set allowedViews(views) {
    this._allowedViews = views;
    this._updateTabStates();
  }

  get allowedViews() {
    return this._allowedViews;
  }

  render() {
    const tabs = [
      { id: "helm", label: "HELM", shortcut: "1", icon: "H" },
      { id: "tactical", label: "TACTICAL", shortcut: "2", icon: "T" },
      { id: "ops", label: "OPS", shortcut: "3", icon: "O" },
      { id: "engineering", label: "ENGINEERING", shortcut: "4", icon: "E" },
      { id: "comms", label: "COMMS", shortcut: "5", icon: "C" },
      { id: "science", label: "SCIENCE", shortcut: "6", icon: "S" },
      { id: "fleet", label: "FLEET", shortcut: "7", icon: "F" },
      { id: "mission", label: "MISSION", shortcut: "8", icon: "M" },
      { id: "editor", label: "EDITOR", shortcut: "9", icon: "W" },
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

        /* Station accent colors — mirrors #view-{name} --view-accent in main.css */
        .tab[data-view="helm"]        { --tab-accent: #6699cc; }
        .tab[data-view="tactical"]    { --tab-accent: #cc4444; }
        .tab[data-view="ops"]         { --tab-accent: #cc8800; }
        .tab[data-view="engineering"] { --tab-accent: #cc6600; }
        .tab[data-view="science"]     { --tab-accent: #00ccaa; }
        .tab[data-view="comms"]       { --tab-accent: #9977dd; }
        .tab[data-view="fleet"]       { --tab-accent: #5588cc; }
        .tab[data-view="mission"]     { --tab-accent: #889900; }

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
          background: var(--tab-accent, var(--status-info, #00aaff));
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
          background: color-mix(in srgb, var(--tab-accent, #00aaff) 15%, transparent);
          color: var(--tab-accent, var(--status-info, #00aaff));
        }

        .tab.locked {
          opacity: 0.25;
          cursor: not-allowed;
          pointer-events: none;
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
        if (tab.classList.contains("locked")) return;
        this.activeView = tab.dataset.view;
      });
    });
  }

  _setupKeyboardShortcuts() {
    const viewMap = { "1": "helm", "2": "tactical", "3": "ops", "4": "engineering", "5": "comms", "6": "science", "7": "fleet", "8": "mission", "9": "editor" };

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
        const targetView = viewMap[e.key];
        // Respect view locking
        if (this._allowedViews && !this._allowedViews.includes(targetView)) return;
        e.preventDefault();
        this.activeView = targetView;
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

  _updateTabStates() {
    const tabs = this.shadowRoot.querySelectorAll(".tab");
    tabs.forEach(tab => {
      const viewId = tab.dataset.view;
      const isLocked = this._allowedViews && !this._allowedViews.includes(viewId);
      tab.classList.toggle("locked", isLocked);
      tab.setAttribute("aria-disabled", isLocked);
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
