/**
 * Single shared target ID store.
 * Used by SensorContacts (write on lock) and FlightComputerPanel,
 * TargetingDisplay, LauncherControl etc. (read to get active target).
 */
import { writable } from "svelte/store";

const _id = writable<string>("");

export const selectedTargetId = {
  subscribe: _id.subscribe,
  set: (id: string) => _id.set(id),
  clear: () => _id.set(""),
};
