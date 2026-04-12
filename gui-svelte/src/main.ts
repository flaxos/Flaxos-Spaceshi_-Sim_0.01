import { get } from "svelte/store";
import { mount } from "svelte";
import App from "./App.svelte";
import { gameState } from "./lib/stores/gameState.js";
import { playerShipId } from "./lib/stores/playerShip.js";
import { wsClient } from "./lib/ws/wsClient.js";

const app = mount(App, {
  target: document.getElementById("app")!,
});

// Expose debug helper
(window as unknown as Record<string, unknown>)._flaxosDebugState = () => {
  const state = get(gameState) as Record<string, unknown>;
  const shipState = (state?.state as Record<string, unknown> | undefined)
    ?? (state?.ship as Record<string, unknown> | undefined)
    ?? null;

  return {
    tier: (window as unknown as Record<string, unknown>).controlTier,
    activeShipId: get(playerShipId),
    shipStateId: shipState?.id ?? null,
    activeScenario: state?.active_scenario ?? null,
    ws: wsClient.getDiagnostics(),
    stateKeys: Object.keys(state ?? {}),
  };
};

export default app;
