import { writable } from "svelte/store";

const _selectedHelmTargetId = writable<string>("");

export const selectedHelmTargetId = {
  subscribe: _selectedHelmTargetId.subscribe,
  set: (value: string) => _selectedHelmTargetId.set(value),
  clear: () => _selectedHelmTargetId.set(""),
};
