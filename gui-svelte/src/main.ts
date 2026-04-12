import { mount } from "svelte";
import App from "./App.svelte";

const app = mount(App, {
  target: document.getElementById("app")!,
});

// Expose debug helper
(window as unknown as Record<string, unknown>)._flaxosDebugState = () => ({
  tier: (window as unknown as Record<string, unknown>).controlTier,
});

export default app;
