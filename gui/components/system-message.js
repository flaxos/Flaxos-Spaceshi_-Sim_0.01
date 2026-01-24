/**
 * System Message Component (Toast Notifications)
 * Toast-style notifications with auto-dismiss and priority levels
 */

class SystemMessages extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._messages = [];
    this._maxMessages = 3;
  }

  connectedCallback() {
    this.render();
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          position: fixed;
          top: 60px;
          right: 16px;
          z-index: 1000;
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-width: 400px;
          pointer-events: none;
        }

        .message {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 12px 16px;
          background: var(--bg-panel, #12121a);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 8px;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
          animation: slideIn 0.25s ease;
          pointer-events: auto;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.85rem;
        }

        .message.info {
          border-left: 3px solid var(--status-info, #00aaff);
        }

        .message.success {
          border-left: 3px solid var(--status-nominal, #00ff88);
        }

        .message.warning {
          border-left: 3px solid var(--status-warning, #ffaa00);
        }

        .message.error,
        .message.critical {
          border-left: 3px solid var(--status-critical, #ff4444);
        }

        .message.critical {
          background: rgba(255, 68, 68, 0.1);
        }

        .message.exiting {
          animation: slideOut 0.2s ease forwards;
        }

        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(20px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }

        @keyframes slideOut {
          from {
            opacity: 1;
            transform: translateX(0);
          }
          to {
            opacity: 0;
            transform: translateX(20px);
          }
        }

        .icon {
          font-size: 1.1rem;
          line-height: 1;
          flex-shrink: 0;
        }

        .message.info .icon { color: var(--status-info, #00aaff); }
        .message.success .icon { color: var(--status-nominal, #00ff88); }
        .message.warning .icon { color: var(--status-warning, #ffaa00); }
        .message.error .icon,
        .message.critical .icon { color: var(--status-critical, #ff4444); }

        .content {
          flex: 1;
          min-width: 0;
        }

        .title {
          font-weight: 600;
          margin-bottom: 4px;
          color: var(--text-bright, #ffffff);
        }

        .text {
          color: var(--text-primary, #e0e0e0);
          word-wrap: break-word;
        }

        .dismiss {
          background: transparent;
          border: none;
          color: var(--text-dim, #555566);
          cursor: pointer;
          padding: 4px;
          font-size: 1rem;
          line-height: 1;
          flex-shrink: 0;
          min-height: auto;
        }

        .dismiss:hover {
          color: var(--text-primary, #e0e0e0);
        }

        .progress {
          position: absolute;
          bottom: 0;
          left: 0;
          height: 2px;
          background: currentColor;
          opacity: 0.3;
          animation: progress linear forwards;
        }

        @keyframes progress {
          from { width: 100%; }
          to { width: 0%; }
        }
      </style>
      <div id="container"></div>
    `;
  }

  /**
   * Show a message
   * @param {object} options - Message options
   * @param {string} options.type - Message type: info, success, warning, error, critical
   * @param {string} options.title - Optional title
   * @param {string} options.text - Message text
   * @param {number} options.duration - Auto-dismiss duration in ms (0 = no auto-dismiss)
   * @returns {string} Message ID
   */
  show(options) {
    const {
      type = "info",
      title = "",
      text = "",
      duration = 5000
    } = options;

    const id = `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    const messageData = { id, type, title, text, duration };
    this._messages.push(messageData);

    // Limit messages
    while (this._messages.length > this._maxMessages) {
      const oldest = this._messages.shift();
      this._removeElement(oldest.id);
    }

    this._renderMessage(messageData);

    // Auto-dismiss (except critical)
    if (duration > 0 && type !== "critical") {
      setTimeout(() => this.dismiss(id), duration);
    }

    return id;
  }

  /**
   * Dismiss a message
   * @param {string} id - Message ID
   */
  dismiss(id) {
    const container = this.shadowRoot.getElementById("container");
    const element = container.querySelector(`[data-id="${id}"]`);

    if (element) {
      element.classList.add("exiting");
      setTimeout(() => {
        this._removeElement(id);
      }, 200);
    }

    this._messages = this._messages.filter(m => m.id !== id);
  }

  /**
   * Dismiss all messages
   */
  dismissAll() {
    const container = this.shadowRoot.getElementById("container");
    container.querySelectorAll(".message").forEach(el => {
      el.classList.add("exiting");
    });

    setTimeout(() => {
      container.innerHTML = "";
    }, 200);

    this._messages = [];
  }

  _renderMessage(data) {
    const container = this.shadowRoot.getElementById("container");

    const el = document.createElement("div");
    el.className = `message ${data.type}`;
    el.dataset.id = data.id;

    const icon = this._getIcon(data.type);

    el.innerHTML = `
      <span class="icon">${icon}</span>
      <div class="content">
        ${data.title ? `<div class="title">${this._escapeHtml(data.title)}</div>` : ""}
        <div class="text">${this._escapeHtml(data.text)}</div>
      </div>
      <button class="dismiss" title="Dismiss">✕</button>
      ${data.duration > 0 && data.type !== "critical" ? 
        `<div class="progress" style="animation-duration: ${data.duration}ms; color: ${this._getColor(data.type)}"></div>` : 
        ""}
    `;

    el.querySelector(".dismiss").addEventListener("click", () => {
      this.dismiss(data.id);
    });

    container.appendChild(el);
  }

  _removeElement(id) {
    const container = this.shadowRoot.getElementById("container");
    const element = container.querySelector(`[data-id="${id}"]`);
    if (element) {
      element.remove();
    }
  }

  _getIcon(type) {
    switch (type) {
      case "success": return "✓";
      case "warning": return "⚠";
      case "error":
      case "critical": return "✕";
      default: return "ℹ";
    }
  }

  _getColor(type) {
    switch (type) {
      case "success": return "#00ff88";
      case "warning": return "#ffaa00";
      case "error":
      case "critical": return "#ff4444";
      default: return "#00aaff";
    }
  }

  _escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // Convenience methods
  info(text, title = "") { return this.show({ type: "info", text, title }); }
  success(text, title = "") { return this.show({ type: "success", text, title }); }
  warning(text, title = "") { return this.show({ type: "warning", text, title }); }
  error(text, title = "") { return this.show({ type: "error", text, title }); }
  critical(text, title = "") { return this.show({ type: "critical", text, title, duration: 0 }); }
}

customElements.define("system-messages", SystemMessages);
export { SystemMessages };
