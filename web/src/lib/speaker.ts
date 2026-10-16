/** Display label for a LiveKit transcription participant. */
export function speakerLabel(identity: string, name?: string): string {
  const trimmed = name?.trim();
  if (trimmed) return trimmed;

  if (identity.startsWith("+") || /^\d/.test(identity)) {
    return "Caller";
  }

  const lower = identity.toLowerCase();
  if (
    lower.includes("kavita") ||
    lower.startsWith("agent-") ||
    lower.startsWith("helpline-")
  ) {
    return "Kavita";
  }

  return identity;
}
