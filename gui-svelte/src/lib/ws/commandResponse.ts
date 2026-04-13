type NestedCommandResponse = {
  ok?: boolean;
  message?: string;
  error?: string;
  reason?: string;
};

type CommandResponse = NestedCommandResponse & {
  response?: NestedCommandResponse;
};

function asCommandResponse(value: unknown): CommandResponse | null {
  if (!value || typeof value !== "object") return null;
  return value as CommandResponse;
}

export function isCommandRejected(value: unknown): boolean {
  const response = asCommandResponse(value);
  if (!response) return false;
  return response.ok === false
    || response.response?.ok === false
    || Boolean(response.error)
    || Boolean(response.response?.error);
}

export function describeCommandFailure(value: unknown, fallback = "Command rejected"): string {
  const response = asCommandResponse(value);
  if (!response) return fallback;
  return String(
    response.error
    ?? response.reason
    ?? response.message
    ?? response.response?.error
    ?? response.response?.reason
    ?? response.response?.message
    ?? fallback
  );
}
