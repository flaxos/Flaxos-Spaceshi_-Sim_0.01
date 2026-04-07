/**
 * WebSocket Client for Flaxos Spaceship Sim GUI
 * Handles connection to the WebSocket-TCP bridge
 */

class WSClient extends EventTarget {
  constructor(url = null) {
    super();
    this.url = url || `ws://${window.location.hostname}:8081`;
    this.socket = null;
    this.status = "disconnected"; // disconnected, connecting, connected
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.reconnectDelay = 1000;
    this.pingInterval = null;
    this.heartbeatInterval = null;
    this.latency = null;
    this.tcpConnected = false;
    this.tcpHost = null;
    this.tcpPort = null;
    this._connectPromise = null;
    this._reconnectTimer = null;

    // Server-assigned client ID (from TCP welcome via bridge)
    this.serverClientId = null;
    // Server mode (station or minimal)
    this.serverMode = null;

    // Request tracking for concurrent command handling
    this._pendingRequests = new Map();
    this._requestIdCounter = 0;

    // Per-command throttle: maps command name -> last send timestamp (ms).
    // Prevents spamming the same command faster than _THROTTLE_MS apart.
    this._commandThrottle = new Map();
  }

  /**
   * Minimum milliseconds between duplicate commands.
   */
  static _THROTTLE_MS = 50;

  /**
   * Commands exempt from throttling (read-only queries that should
   * always go through immediately).
   */
  static _THROTTLE_EXEMPT = new Set([
    "get_state",
    "get_mission",
    "get_events",
    "get_comms_choices",
    "helm_queue_status",
    "combat_status",
    "weapon_status",
    "_ping",
    "heartbeat",
  ]);

  /**
   * Check whether a command should be silently dropped due to throttling.
   * Returns true if the same command was sent within _THROTTLE_MS.
   * Side-effect: records the timestamp when returning false (allowed).
   * @param {string} command - Command name
   * @returns {boolean} true = drop this send, false = allow
   */
  _shouldThrottle(command) {
    if (WSClient._THROTTLE_EXEMPT.has(command)) return false;

    const now = Date.now();
    const lastSent = this._commandThrottle.get(command) || 0;
    if (now - lastSent < WSClient._THROTTLE_MS) return true;

    this._commandThrottle.set(command, now);
    return false;
  }

  /**
   * Whether the WebSocket is currently connected.
   */
  get isConnected() {
    return this.status === "connected" &&
      this.socket !== null &&
      this.socket.readyState === WebSocket.OPEN;
  }

  /**
   * Connect to the WebSocket bridge
   */
  connect() {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }
    if (this.socket && this.socket.readyState === WebSocket.CONNECTING && this._connectPromise) {
      return this._connectPromise;
    }
    if (this.status === "connecting" && this._connectPromise) {
      return this._connectPromise;
    }

    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }

    this._connectPromise = new Promise((resolve, reject) => {
      this._setStatus("connecting");

      try {
        this.socket = new WebSocket(this.url);
      } catch (error) {
        this._setStatus("disconnected");
        this._connectPromise = null;
        reject(error);
        return;
      }

      const timeout = setTimeout(() => {
        this.socket.close();
        this._setStatus("disconnected");
        this._connectPromise = null;
        reject(new Error("Connection timeout"));
      }, 10000);

      this.socket.onopen = () => {
        clearTimeout(timeout);

        // If a game code is configured, send auth as the very first message
        // before any pings or commands.
        const gameCode = window.GAME_CODE;
        if (gameCode) {
          try {
            this.socket.send(JSON.stringify({ type: "auth", code: gameCode }));
          } catch (err) {
            console.error("Failed to send auth message:", err);
          }
        }

        this._setStatus("connected");
        this.reconnectAttempts = 0;
        this._startPing();
        this._startHeartbeat();
        this._connectPromise = null;
        resolve();
      };

      this.socket.onclose = (event) => {
        clearTimeout(timeout);
        this._setStatus("disconnected");
        this._stopPing();
        this._stopHeartbeat();
        this._clearPendingRequests();
        this._connectPromise = null;
        this._emit("close", { code: event.code, reason: event.reason });
        this._attemptReconnect();
      };

      this.socket.onerror = (error) => {
        clearTimeout(timeout);
        this._connectPromise = null;
        this._emit("error", { error });
      };

      this.socket.onmessage = (event) => {
        this._handleMessage(event.data);
      };
    });

    return this._connectPromise;
  }

  /**
   * Disconnect from WebSocket
   */
  disconnect() {
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnect
    this._stopPing();
    this._stopHeartbeat();
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this._setStatus("disconnected");
  }

  /**
   * Send a command to the server
   * @param {string} cmd - Command name
   * @param {object} args - Command arguments
   * @returns {Promise<object>} Server response
   */
  send(cmd, args = {}) {
    if (this._shouldThrottle(cmd)) {
      return Promise.resolve({ ok: false, reason: "throttled" });
    }

    return new Promise((resolve, reject) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        reject(new Error("Not connected"));
        return;
      }

      // Generate unique request ID for tracking and correlation
      const requestId = ++this._requestIdCounter;
      // Include _request_id in the message for server-side correlation
      const message = JSON.stringify({ cmd, _request_id: requestId, ...args });

      // Timeout after 15 seconds
      const timeout = setTimeout(() => {
        this._pendingRequests.delete(requestId);
        reject(new Error("Response timeout"));
      }, 15000);

      // Store request handler with its timeout, keyed by requestId
      this._pendingRequests.set(requestId, { resolve, reject, timeout, cmd });

      try {
        this.socket.send(message);
      } catch (error) {
        clearTimeout(timeout);
        this._pendingRequests.delete(requestId);
        reject(error);
      }
    });
  }

  /**
   * Resolve a pending request by its request ID
   * Called by _handleMessage when a response is received
   * @param {number|null} requestId - The request ID from the response
   * @param {object} data - Response data
   */
  _resolvePendingRequest(requestId, data) {
    // Try to match by request ID first (preferred)
    if (requestId !== null && requestId !== undefined && this._pendingRequests.has(requestId)) {
      const { resolve, timeout } = this._pendingRequests.get(requestId);
      clearTimeout(timeout);
      this._pendingRequests.delete(requestId);
      resolve(data);
      return;
    }

    // Fallback: If no request ID in response, use FIFO (for backward compatibility)
    // This handles cases where the server doesn't echo the request ID
    const iterator = this._pendingRequests.entries().next();
    if (!iterator.done) {
      const [fallbackId, { resolve, timeout }] = iterator.value;
      clearTimeout(timeout);
      this._pendingRequests.delete(fallbackId);
      resolve(data);
    } else {
      // No pending request - emit as general response event
      this._emit("response", data);
    }
  }

  /**
   * Reject a pending request by its request ID (for error responses)
   * @param {number|null} requestId - The request ID from the error response
   * @param {object} errorData - Error data
   */
  _rejectPendingRequest(requestId, errorData) {
    // Try to match by request ID first
    if (requestId !== null && requestId !== undefined && this._pendingRequests.has(requestId)) {
      const { reject, timeout } = this._pendingRequests.get(requestId);
      clearTimeout(timeout);
      this._pendingRequests.delete(requestId);
      reject(new Error(errorData?.error || "Server error"));
      return;
    }

    // No matching request - error will be emitted as general event only
  }

  /**
   * Send command and ignore response
   * @param {string} cmd - Command name
   * @param {object} args - Command arguments
   */
  sendAsync(cmd, args = {}) {
    if (this._shouldThrottle(cmd)) return;

    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    const message = JSON.stringify({ cmd, ...args });
    try {
      this.socket.send(message);
    } catch (error) {
      console.error("Send error:", error);
    }
  }

  /**
   * Handle incoming WebSocket message
   */
  _handleMessage(rawData) {
    let data;
    try {
      data = JSON.parse(rawData);
    } catch (error) {
      console.error("Invalid JSON from server:", rawData);
      return;
    }

    const type = data.type;
    const payload = data.data;

    switch (type) {
      case "connection_status":
        this.tcpConnected = payload.tcp_connected;
        this.tcpHost = payload.tcp_host;
        this.tcpPort = payload.tcp_port;
        // Capture server-assigned client_id from bridge (per-client TCP)
        if (payload.client_id) {
          this.serverClientId = payload.client_id;
        }
        if (payload.server_mode) {
          this.serverMode = payload.server_mode;
        }
        this._emit("connection_status", payload);
        break;

      case "pong":
        if (payload.timestamp) {
          this.latency = Date.now() - payload.timestamp;
          this._emit("latency", { latency: this.latency });
        }
        break;

      case "response":
        // Extract request ID from response payload for correlation
        const requestId = payload?._request_id;
        // Remove _request_id from payload before passing to handler
        if (requestId !== undefined) {
          delete payload._request_id;
        }
        // Route response to the matching pending request
        this._resolvePendingRequest(requestId, payload);
        break;

      case "error":
        // Check if error has a request ID for correlation
        const errorRequestId = payload?._request_id;
        if (errorRequestId !== undefined) {
          delete payload._request_id;
        }
        // If we can match the error to a pending request, reject it
        this._rejectPendingRequest(errorRequestId, payload);
        // Also emit the error event for general handling
        this._emit("server_error", payload);
        break;

      case "event":
        this._emit("event", payload);
        break;

      default:
        this._emit("message", data);
    }
  }

  /**
   * Update connection status and emit event
   */
  _setStatus(status) {
    const oldStatus = this.status;
    this.status = status;
    if (oldStatus !== status) {
      this._emit("status_change", { status, oldStatus });
    }
  }

  /**
   * Emit a custom event
   */
  _emit(eventName, detail = {}) {
    this.dispatchEvent(new CustomEvent(eventName, { detail }));
  }

  /**
   * Attempt automatic reconnection
   */
  _attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      return;
    }
    if (this._reconnectTimer) {
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.min(this.reconnectAttempts, 5);

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      if (this.status === "disconnected") {
        this.connect().catch(() => {
          // Will auto-retry on failure
        });
      }
    }, delay);
  }

  /**
   * Start periodic ping for latency measurement
   */
  _startPing() {
    this._stopPing();
    this.pingInterval = setInterval(() => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.sendAsync("_ping", { timestamp: Date.now() });
      }
    }, 5000);
  }

  /**
   * Stop ping interval
   */
  _stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  /**
   * Start periodic heartbeat to keep session alive on the server.
   * Sends a fire-and-forget heartbeat command every 30 seconds.
   */
  _startHeartbeat() {
    this._stopHeartbeat();
    this.heartbeatInterval = setInterval(() => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.sendAsync("heartbeat");
      }
    }, 30000);
  }

  /**
   * Stop heartbeat interval
   */
  _stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Get current connection info
   */
  getConnectionInfo() {
    return {
      status: this.status,
      url: this.url,
      tcpConnected: this.tcpConnected,
      tcpHost: this.tcpHost,
      tcpPort: this.tcpPort,
      latency: this.latency
    };
  }

  /**
   * Send a ship command (auto-injects ship parameter from stateManager)
   * Use this for commands that require a ship parameter.
   * @param {string} cmd - Command name
   * @param {object} args - Command arguments
   * @returns {Promise<object>} Server response
   */
  sendShipCommand(cmd, args = {}) {
    if (this._shouldThrottle(cmd)) {
      return Promise.resolve({ ok: false, reason: "throttled" });
    }

    // Import stateManager dynamically to avoid circular dependency
    const { stateManager } = window._flaxosModules || {};
    const shipId = stateManager?.getPlayerShipId?.();
    
    if (!shipId) {
      const error = new Error(`No player ship ID set. Cannot send ship command: ${cmd}`);
      console.error(error.message);
      return Promise.reject(error);
    }
    
    return this.send(cmd, { ship: shipId, ...args });
  }

  /**
   * Send a ship command without waiting for response
   * @param {string} cmd - Command name
   * @param {object} args - Command arguments
   * @returns {boolean} True if command was sent, false if no ship ID
   */
  sendShipCommandAsync(cmd, args = {}) {
    if (this._shouldThrottle(cmd)) return false;

    const { stateManager } = window._flaxosModules || {};
    const shipId = stateManager?.getPlayerShipId?.();
    
    if (!shipId) {
      console.error(`No player ship ID set. Cannot send ship command: ${cmd}`);
      return false;
    }
    
    this.sendAsync(cmd, { ship: shipId, ...args });
    return true;
  }

  /**
   * Clear all pending requests (e.g., on disconnect)
   */
  _clearPendingRequests() {
    for (const [requestId, { reject, timeout }] of this._pendingRequests) {
      clearTimeout(timeout);
      reject(new Error("Connection closed"));
    }
    this._pendingRequests.clear();
  }
}

// Bootstrap game code from URL query parameter (?game_code=XXXX).
// Can also be set directly: window.GAME_CODE = "XXXX" before connecting.
try {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("game_code");
  if (code) {
    window.GAME_CODE = code;
  }
} catch (_) {
  // Ignore — running outside a browser (tests, etc.)
}

// Export singleton instance
const wsClient = new WSClient();
export { WSClient, wsClient };
