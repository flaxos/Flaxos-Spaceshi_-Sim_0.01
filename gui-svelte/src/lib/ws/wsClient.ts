/**
 * WebSocket Client — TypeScript port of gui/js/ws-client.js
 * Keeps ALL existing logic: reconnect, throttle, request ID correlation,
 * 15s timeout, heartbeat, ping, sendShipCommand, send.
 * Protocol is unchanged.
 *
 * Ship ID is injected via setActiveShipId() to avoid circular deps with stores.
 */

type ConnectionStatus = "disconnected" | "connecting" | "connected";

interface PendingRequest {
  resolve: (data: unknown) => void;
  reject: (err: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
  cmd: string;
}

const THROTTLE_MS = 50;
const THROTTLE_EXEMPT = new Set([
  "get_state",
  "get_mission",
  "get_events",
  "get_combat_log",
  "get_mission_hints",
  "get_tick_metrics",
  "get_station_messages",
  "get_comms_choices",
  "crew_status",
  "fleet_status",
  "fleet_tactical",
  "auto_fleet_status",
  "get_draw_profile",
  "get_power_profiles",
  "get_nav_solutions",
  "get_target_solution",
  "assess_damage",
  "helm_queue_status",
  "combat_status",
  "weapon_status",
  "_ping",
  "_discover",
  "_resume_session",
  "heartbeat",
  "register_client",
  "assign_ship",
  "claim_station",
  "release_station",
  "my_status",
  "station_status",
  "list_scenarios",
  "list_ships",
  "list_ship_classes",
  "get_ship_classes_full",
  "save_ship_class",
  "load_scenario",
  "save_scenario",
  "get_scenario_yaml",
  "generate_skirmish",
  "campaign_new",
  "campaign_save",
  "campaign_load",
  "campaign_status",
  "pause",
  "set_time_scale",
  "rcon_auth",
  "rcon_reload",
  "rcon_load",
  "rcon_pause",
  "rcon_timescale",
  "rcon_kick",
  "rcon_status",
  "rcon_restart",
  "rcon_set_password",
  "rcon_list",
]);

class WSClient extends EventTarget {
  url: string;
  socket: WebSocket | null = null;
  status: ConnectionStatus = "disconnected";
  reconnectAttempts = 0;
  maxReconnectAttempts = 10;
  reconnectDelay = 1000;
  pingInterval: ReturnType<typeof setInterval> | null = null;
  heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  latency: number | null = null;
  tcpConnected = false;
  tcpHost: string | null = null;
  tcpPort: number | null = null;
  serverClientId: string | null = null;
  serverMode: string | null = null;

  // Injected by playerShip store after init to avoid circular dep
  private _activeShipId: string | null = null;

  private _connectPromise: Promise<void> | null = null;
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _pendingRequests = new Map<number, PendingRequest>();
  private _requestIdCounter = 0;
  private _blockedCommands = new Map<string, number>();
  private _blockedCommandTotal = 0;
  private _commandThrottle = new Map<string, number>();
  private _rconToken: string | null = null;

  constructor(url?: string) {
    super();
    this.url = url ?? `ws://${window.location.hostname}:8081`;

    // Bootstrap game code from URL query parameter
    try {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("game_code");
      if (code) (window as unknown as Record<string, unknown>).GAME_CODE = code;
    } catch (_) { /* outside browser */ }
  }

  /** Called by playerShip store when ship ID changes. */
  setActiveShipId(id: string | null): void {
    this._activeShipId = id;
  }

  get isConnected(): boolean {
    return (
      this.status === "connected" &&
      this.socket !== null &&
      this.socket.readyState === WebSocket.OPEN
    );
  }

  private _shouldThrottle(cmd: string): boolean {
    if (THROTTLE_EXEMPT.has(cmd)) return false;
    const now = Date.now();
    const last = this._commandThrottle.get(cmd) ?? 0;
    if (now - last < THROTTLE_MS) return true;
    this._commandThrottle.set(cmd, now);
    return false;
  }

  connect(): Promise<void> {
    if (this.socket?.readyState === WebSocket.OPEN) return Promise.resolve();
    if (this.socket?.readyState === WebSocket.CONNECTING && this._connectPromise) {
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
        this.socket?.close();
        this._setStatus("disconnected");
        this._connectPromise = null;
        reject(new Error("Connection timeout"));
      }, 10000);

      this.socket.onopen = () => {
        clearTimeout(timeout);
        const gameCode = (window as unknown as Record<string, unknown>).GAME_CODE as string | undefined;
        if (gameCode && this.socket) {
          try { this.socket.send(JSON.stringify({ type: "auth", code: gameCode })); }
          catch (err) { console.error("Failed to send auth:", err); }
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

      this.socket.onerror = () => {
        clearTimeout(timeout);
        this._connectPromise = null;
        this._emit("error", {});
      };

      this.socket.onmessage = (event) => {
        this._handleMessage(event.data as string);
      };
    });

    return this._connectPromise;
  }

  disconnect(): void {
    this.reconnectAttempts = this.maxReconnectAttempts;
    this._stopPing();
    this._stopHeartbeat();
    if (this._reconnectTimer) { clearTimeout(this._reconnectTimer); this._reconnectTimer = null; }
    if (this.socket) { this.socket.close(); this.socket = null; }
    this._setStatus("disconnected");
  }

  send(cmd: string, args: Record<string, unknown> = {}): Promise<unknown> {
    if (this._shouldThrottle(cmd)) return Promise.resolve({ ok: false, reason: "throttled" });

    return new Promise((resolve, reject) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        reject(new Error("Not connected"));
        return;
      }

      const requestId = ++this._requestIdCounter;
      const message = JSON.stringify({ cmd, _request_id: requestId, ...args });

      const timeout = setTimeout(() => {
        this._pendingRequests.delete(requestId);
        reject(new Error("Response timeout"));
      }, 15000);

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

  sendAsync(cmd: string, args: Record<string, unknown> = {}): void {
    if (this._shouldThrottle(cmd)) return;
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
    const message = JSON.stringify({ cmd, ...args });
    try { this.socket.send(message); } catch (err) { console.error("Send error:", err); }
  }

  sendShipCommand(cmd: string, args: Record<string, unknown> = {}): Promise<unknown> {
    const shipId = (args.ship as string | undefined) ?? this._activeShipId;

    if (!shipId) {
      const count = (this._blockedCommands.get(cmd) ?? 0) + 1;
      this._blockedCommands.set(cmd, count);
      this._blockedCommandTotal += 1;
      return Promise.resolve({ ok: false, error: "no_ship_id" });
    }

    return this.send(cmd, { ship: shipId, ...args });
  }

  sendShipCommandAsync(cmd: string, args: Record<string, unknown> = {}): boolean {
    const shipId = (args.ship as string | undefined) ?? this._activeShipId;
    if (!shipId) {
      const count = (this._blockedCommands.get(cmd) ?? 0) + 1;
      this._blockedCommands.set(cmd, count);
      this._blockedCommandTotal += 1;
      return false;
    }
    this.sendAsync(cmd, { ship: shipId, ...args });
    return true;
  }

  async rconAuth(password: string): Promise<unknown> {
    const resp = await this.send("rcon_auth", { password }) as { ok: boolean; token?: string };
    if (resp?.ok && resp.token) this._rconToken = resp.token;
    return resp;
  }

  hasRconAuth(): boolean {
    return Boolean(this._rconToken);
  }

  clearRconAuth(): void {
    this._rconToken = null;
  }

  async rcon(cmd: string, args: Record<string, unknown> = {}): Promise<unknown> {
    if (!this._rconToken) return { ok: false, error: "Not authenticated" };
    const response = await this.send(cmd, { ...args, token: this._rconToken }) as {
      ok?: boolean;
      error?: string;
    };
    if (response?.ok === false && response.error === "Unauthorized") {
      this.clearRconAuth();
    }
    return response;
  }

  getConnectionInfo() {
    return {
      status: this.status,
      url: this.url,
      tcpConnected: this.tcpConnected,
      tcpHost: this.tcpHost,
      tcpPort: this.tcpPort,
      latency: this.latency,
    };
  }

  getDiagnostics() {
    return {
      status: this.status,
      isConnected: this.isConnected,
      tcpConnected: this.tcpConnected,
      latency: this.latency,
      pendingRequests: this._pendingRequests.size,
      blockedCommands: Object.fromEntries(this._blockedCommands.entries()),
      blockedCommandTotal: this._blockedCommandTotal,
    };
  }

  private _handleMessage(rawData: string): void {
    let data: { type: string; data: Record<string, unknown> };
    try { data = JSON.parse(rawData) as typeof data; }
    catch { console.error("Invalid JSON:", rawData); return; }

    const { type, data: payload } = data;

    switch (type) {
      case "connection_status":
        this.tcpConnected = payload.tcp_connected as boolean;
        this.tcpHost = payload.tcp_host as string;
        this.tcpPort = payload.tcp_port as number;
        if (payload.client_id) this.serverClientId = payload.client_id as string;
        if (payload.server_mode) this.serverMode = payload.server_mode as string;
        this._emit("connection_status", payload);
        break;

      case "pong":
        if (payload.timestamp) {
          this.latency = Date.now() - (payload.timestamp as number);
          this._emit("latency", { latency: this.latency });
        }
        break;

      case "response": {
        const requestId = payload._request_id as number | undefined;
        if (requestId !== undefined) delete payload._request_id;
        this._resolvePendingRequest(requestId ?? null, payload);
        break;
      }

      case "error": {
        const errorRequestId = payload._request_id as number | undefined;
        if (errorRequestId !== undefined) delete payload._request_id;
        this._rejectPendingRequest(errorRequestId ?? null, payload);
        this._emit("server_error", payload);
        break;
      }

      case "event":
        this._emit("event", payload);
        break;

      default:
        this._emit("message", data as unknown as Record<string, unknown>);
    }
  }

  private _resolvePendingRequest(requestId: number | null, data: unknown): void {
    if (requestId !== null && this._pendingRequests.has(requestId)) {
      const { resolve, timeout } = this._pendingRequests.get(requestId)!;
      clearTimeout(timeout);
      this._pendingRequests.delete(requestId);
      resolve(data);
      return;
    }
    // FIFO fallback for servers that don't echo request ID
    const iter = this._pendingRequests.entries().next();
    if (!iter.done) {
      const [fallbackId, { resolve, timeout }] = iter.value as [number, PendingRequest];
      clearTimeout(timeout);
      this._pendingRequests.delete(fallbackId);
      resolve(data);
    } else {
      this._emit("response", data as Record<string, unknown>);
    }
  }

  private _rejectPendingRequest(requestId: number | null, errorData: unknown): void {
    if (requestId !== null && this._pendingRequests.has(requestId)) {
      const { reject, timeout } = this._pendingRequests.get(requestId)!;
      clearTimeout(timeout);
      this._pendingRequests.delete(requestId);
      reject(new Error((errorData as Record<string, unknown>)?.error as string || "Server error"));
    }
  }

  private _setStatus(status: ConnectionStatus): void {
    const oldStatus = this.status;
    this.status = status;
    if (oldStatus !== status) this._emit("status_change", { status, oldStatus });
  }

  private _emit(eventName: string, detail: Record<string, unknown> = {}): void {
    this.dispatchEvent(new CustomEvent(eventName, { detail }));
  }

  private _attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    if (this._reconnectTimer) return;
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.min(this.reconnectAttempts, 5);
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      if (this.status === "disconnected") {
        this.connect().catch(() => { /* will retry */ });
      }
    }, delay);
  }

  private _startPing(): void {
    this._stopPing();
    this.pingInterval = setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.sendAsync("_ping", { timestamp: Date.now() });
      }
    }, 5000);
  }

  private _stopPing(): void {
    if (this.pingInterval) { clearInterval(this.pingInterval); this.pingInterval = null; }
  }

  private _startHeartbeat(): void {
    this._stopHeartbeat();
    this.heartbeatInterval = setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) this.sendAsync("heartbeat");
    }, 30000);
  }

  private _stopHeartbeat(): void {
    if (this.heartbeatInterval) { clearInterval(this.heartbeatInterval); this.heartbeatInterval = null; }
  }

  private _clearPendingRequests(): void {
    for (const { reject, timeout } of this._pendingRequests.values()) {
      clearTimeout(timeout);
      reject(new Error("Connection closed"));
    }
    this._pendingRequests.clear();
  }
}

export const wsClient = new WSClient();
export type { ConnectionStatus };
