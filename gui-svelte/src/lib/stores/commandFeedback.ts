import { writable } from "svelte/store";

export interface CommandFailure { command: string; message: string; }
export const commandFeedback = writable<CommandFailure | null>(null);

export function reportCommandFailure(command: string, message: string): void {
  commandFeedback.set({ command, message });
}
