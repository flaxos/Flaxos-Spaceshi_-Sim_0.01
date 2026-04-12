import { writable } from "svelte/store";

export const selectedTacticalTargetId = writable("");
export const selectedLauncherType = writable<"torpedo" | "missile">("torpedo");
