/**
 * WebSocket Client for Flaxos Spaceship Sim GUI
 * Handles connection to the WebSocket-TCP bridge
 */

class WSClient extends EventTarget {
  constructor(url = null) {
    super();
    this.url = url || `ws://${window.location.hostname}:8080`;
    this.socket = null;
    this.status = "disconnected"; // disconnected, connecting, connected
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.reconnectDelay = 1000;
    this.pingInterval = null;
    this.latency = null;
    this.tcpConnected = false;
    this.tcpHost = null;
    this.tcpPort = null;
    this._connectPromise = null;
    this._reconnectTimer = null;
    
    // Request tracking for concurrent command handling
    this._pendingRequests = new Map();
    this._requestIdCounter = 0;
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
        this._setStatus("connected");
        this.reconnectAttempts = 0;
        this._startPing();
        this._connectPromise = null;
        resolve();
      };

      this.socket.onclose = (event) => {
        clearTimeout(timeout);
        this._setStatus("disconnected");
        this._stopPing();
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
    return new Promise((resolve, reject) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        reject(new Error("Not connected"));
        return;
      }

      // Generate unique request ID for tracking and correlation
      const requestId = `req_${++this._requestIdCounter}`;
      const message = JSON.stringify({ cmd, _request_id: requestId, ...args });

      // Timeout after 15 seconds
      const timeout = setTimeout(() => {
        this._pendingRequests.delete(requestId);
        reject(new Error("Response timeout"));
      }, 15000);

      // Store request handler with its timeout
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
   * Resolve a pending request with a response
   * Called by _handleMessage when a response is received
   * @param {object} data - Response data
   */
  _resolveNextPendingRequest(data) {
    // Try to match by request ID first (if server echoed it back)
    const requestId = data._request_id;
    if (requestId && this._pendingRequests.has(requestId)) {
      const { resolve, timeout } = this._pendingRequests.get(requestId);
      clearTimeout(timeout);
      this._pendingRequests.delete(requestId);
      // Remove the internal _request_id from the response data
      const { _request_id, ...responseData } = data;
      resolve(responseData);
      return;
    }

    // Fallback to FIFO for backwards compatibility (legacy servers)
    const iterator = this._pendingRequests.entries().next();
    if (!iterator.done) {
      const [reqId, { resolve, timeout }] = iterator.value;
      clearTimeout(timeout);
      this._pendingRequests.delete(reqId);
      resolve(data);
    } else {
      // No pending request - emit as general response event
      this._emit("response", data);
    }
  }

  /**
   * Send command and ignore response
   * @param {string} cmd - Command name
   * @param {object} args - Command arguments
   */
  sendAsync(cmd, args = {}) {
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
        this._emit("connection_status", payload);
        break;

      case "pong":
        if (payload.timestamp) {
          this.latency = Date.now() - payload.timestamp;
          this._emit("latency", { latency: this.latency });
        }
        break;

      case "response":
        // Route response to the next pending request in queue
        this._resolveNextPendingRequest(payload);
        break;

      case "error":
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

// Export singleton instance
const wsClient = new WSClient();
export { WSClient, wsClient };
