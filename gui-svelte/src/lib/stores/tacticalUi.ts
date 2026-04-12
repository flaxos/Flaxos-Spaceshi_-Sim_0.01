// Re-export from shared store so existing imports keep working
export { selectedTargetId as selectedTacticalTargetId } from "./selectedTarget.js";
export { writable } from "svelte/store";
import { writable } from "svelte/store";
export const selectedLauncherType = writable<"torpedo" | "missile">("torpedo");
