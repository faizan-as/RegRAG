import { ApiClient } from "@/lib/api/client";

const FALLBACK_FILENAME = "download.bin";

function sanitizeFilename(filename: string): string {
  const trimmed = filename.trim().replace(/^\.+/, "");
  const cleaned = trimmed
    .replace(/[\u0000-\u001f\u007f]+/g, "")
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, " ")
    .trim();

  return cleaned || FALLBACK_FILENAME;
}

export function parseFilenameFromContentDisposition(
  contentDisposition: string | null,
): string | undefined {
  if (!contentDisposition) {
    return undefined;
  }

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return sanitizeFilename(decodeURIComponent(utf8Match[1]));
    } catch {
      return sanitizeFilename(utf8Match[1]);
    }
  }

  const quotedMatch = contentDisposition.match(/filename="([^"]+)"/i);
  if (quotedMatch?.[1]) {
    return sanitizeFilename(quotedMatch[1]);
  }

  const plainMatch = contentDisposition.match(/filename=([^;]+)/i);
  if (plainMatch?.[1]) {
    return sanitizeFilename(plainMatch[1]);
  }

  return undefined;
}

export function triggerBrowserBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = sanitizeFilename(filename);
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export type AuthenticatedBlobResource = {
  blob: Blob;
  objectUrl: string;
  contentType: string;
  revoke: () => void;
};

export async function createAuthenticatedBlobResource(args: {
  apiClient: ApiClient;
  documentId: string;
  artifactId: string;
  signal?: AbortSignal;
}): Promise<AuthenticatedBlobResource> {
  const response = await args.apiClient.getArtifactBlob(args.documentId, args.artifactId, {
    signal: args.signal,
  });
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  let revoked = false;

  return {
    blob,
    objectUrl,
    contentType: response.headers.get("content-type") ?? blob.type ?? "",
    revoke() {
      if (revoked) {
        return;
      }
      revoked = true;
      URL.revokeObjectURL(objectUrl);
    },
  };
}

export async function downloadArtifactWithAuth(args: {
  apiClient: ApiClient;
  documentId: string;
  artifactId: string;
  fallbackFilename?: string;
  signal?: AbortSignal;
}): Promise<string> {
  const response = await args.apiClient.getArtifactBlob(args.documentId, args.artifactId, {
    signal: args.signal,
  });
  const blob = await response.blob();
  const headerFilename = parseFilenameFromContentDisposition(
    response.headers.get("content-disposition"),
  );
  const filename = headerFilename ?? sanitizeFilename(args.fallbackFilename ?? FALLBACK_FILENAME);
  triggerBrowserBlobDownload(blob, filename);
  return filename;
}

export async function downloadExportWithAuth(args: {
  apiClient: ApiClient;
  exportId: string;
  fallbackFilename?: string;
  signal?: AbortSignal;
}): Promise<string> {
  const response = await args.apiClient.downloadExport(args.exportId, {
    signal: args.signal,
  });
  const blob = await response.blob();
  const headerFilename = parseFilenameFromContentDisposition(
    response.headers.get("content-disposition"),
  );
  const filename = headerFilename ?? sanitizeFilename(args.fallbackFilename ?? FALLBACK_FILENAME);
  triggerBrowserBlobDownload(blob, filename);
  return filename;
}
