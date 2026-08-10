const INVALID_NEXT = "/research";

export function normalizeRelativeNextPath(next: string | null | undefined): string {
  if (!next) {
    return INVALID_NEXT;
  }

  const trimmed = next.trim();
  if (!trimmed.startsWith("/")) {
    return INVALID_NEXT;
  }

  if (trimmed.startsWith("//")) {
    return INVALID_NEXT;
  }

  if (trimmed.includes("\\")) {
    return INVALID_NEXT;
  }

  try {
    const parsed = new URL(trimmed, "http://localhost");
    if (parsed.origin !== "http://localhost") {
      return INVALID_NEXT;
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return INVALID_NEXT;
  }
}
