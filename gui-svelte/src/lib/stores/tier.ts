/**
 * tier store — control tier selection.
 * Persists to localStorage, updates body class + window.controlTier.
 */

import { writable } from "svelte/store";

export type Tier = "manual" | "raw" | "arcade" | "cpu-assist";

const STORAGE_KEY = "flaxos-control-tier";
const VALID: Tier[] = ["manual", "raw", "arcade", "cpu-assist"];
const DEFAULT: Tier = "arcade";

function loadSaved(): Tier {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && VALID.includes(stored as Tier)) return stored as Tier;
  } catch { /* SSR / private browsing */ }
  return DEFAULT;
}

function applyTier(t: Tier): void {
  // Update body class
  VALID.forEach((id) => document.body.classList.remove(`tier-${id}`));
  document.body.classList.add(`tier-${t}`);
  // Update global (legacy components read this)
  (window as unknown as Record<string, unknown>).controlTier = t;
  // Persist
  try { localStorage.setItem(STORAGE_KEY, t); } catch { /* private browsing */ }
}

const _tier = writable<Tier>(loadSaved());

// Apply on every change
_tier.subscribe((t) => {
  if (typeof document !== "undefined") applyTier(t);
});

export const tier = {
  subscribe: _tier.subscribe,
  set: (t: Tier) => {
    if (!VALID.includes(t)) return;
    _tier.set(t);
  },
  update: _tier.update,
};
