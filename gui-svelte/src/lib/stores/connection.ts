/**
 * connection store — WebSocket connection state.
 * Subscribes to wsClient events to stay in sync.
 */

import { writable } from "svelte/store";
import { wsClient } from "../ws/wsClient.js";
import type { ConnectionStatus } from "../ws/wsClient.js";

interface ConnectionState {
  status: ConnectionStatus;
  latency: number | null;
  tcpConnected: boolean;
}

const _connection = writable<ConnectionState>({
  status: wsClient.status,
  latency: null,
  tcpConnected: false,
});

wsClient.addEventListener("status_change", (e) => {
  const { status } = (e as CustomEvent<{ status: ConnectionStatus }>).detail;
  _connection.update((prev) => ({ ...prev, status }));
});

wsClient.addEventListener("latency", (e) => {
  const { latency } = (e as CustomEvent<{ latency: number }>).detail;
  _connection.update((prev) => ({ ...prev, latency }));
});

wsClient.addEventListener("connection_status", (e) => {
  const detail = (e as CustomEvent<{ tcp_connected: boolean }>).detail;
  _connection.update((prev) => ({ ...prev, tcpConnected: detail.tcp_connected }));
});

export const connection = { subscribe: _connection.subscribe };
