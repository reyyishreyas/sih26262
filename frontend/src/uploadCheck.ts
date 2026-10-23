/**
 * Client-side upload checks.
 *
 * These mirror the server's rules (app/services/upload_validation.py) exactly —
 * the same size limit, the same three allowed types, the same magic-byte
 * sniffing — so a file the browser accepts will also be accepted by the API.
 * They exist to fail fast on a slow connection: a 10 MB file that takes five
 * minutes to upload only to be rejected is the exact pain this prevents.
 *
 * The checks are pure and take the already-read bytes, so they are unit
 * testable and usable from the hook below.
 */

/** Same default as backend Settings.max_upload_bytes. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

/** Same three types as backend Settings.allowed_upload_types, in accept order. */
export const ACCEPTED_TYPES = [
  { mime: "application/pdf", label: "PDF", extensions: ".pdf" },
  { mime: "image/png", label: "PNG image", extensions: ".png" },
  { mime: "image/jpeg", label: "JPEG image", extensions: ".jpg,.jpeg" },
] as const;

/** The accept attribute for the file input, built from the list above. */
export const ACCEPT_ATTRIBUTE = ACCEPTED_TYPES.map((t) => t.extensions).join(",");

/** Same magic-byte prefixes as backend _MAGIC_TYPES. */
const MAGIC_TYPES: Array<{ prefix: Uint8Array; mime: string }> = [
  { prefix: new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]), mime: "application/pdf" }, // %PDF-
  {
    prefix: new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    mime: "image/png",
  },
  { prefix: new Uint8Array([0xff, 0xd8, 0xff]), mime: "image/jpeg" },
];

function startsWith(head: Uint8Array, prefix: Uint8Array): boolean {
  if (head.length < prefix.length) return false;
  for (let i = 0; i < prefix.length; i += 1) {
    if (head[i] !== prefix[i]) return false;
  }
  return true;
}

/** Detect the real type from the bytes, ignoring what the file claims to be. */
function sniffMime(head: Uint8Array): string | null {
  for (const { prefix, mime } of MAGIC_TYPES) {
    if (startsWith(head, prefix)) return mime;
  }
  return null;
}

export interface UploadCheck {
  /** True only when the file passes every check and may be uploaded. */
  ok: boolean;
  /** A friendly, plain-language problem to show the user, or null if fine. */
  message: string | null;
  /** The type detected from the file's actual bytes, if recognisable. */
  detectedMime: string | null;
}

const OK: UploadCheck = { ok: true, message: null, detectedMime: null };

function fail(message: string, detectedMime: string | null = null): UploadCheck {
  return { ok: false, message, detectedMime };
}

/**
 * Validate a chosen file from its head bytes. Pure: same inputs, same output.
 *
 * The order matters for a stressed user — size first (the most common and the
 * clearest to fix), then emptiness, then whether the bytes are really one of
 * the three supported formats, which is what catches a mislabelled or
 * password-protected file without ever sending it.
 */
export function checkUpload(
  file: { name: string; size: number } | null,
  head: Uint8Array | null,
): UploadCheck {
  if (!file) return OK;

  if (file.size > MAX_UPLOAD_BYTES) {
    const mb = (MAX_UPLOAD_BYTES / (1024 * 1024)).toFixed(0);
    return fail(
      `This file is too large (${formatBytes(file.size)}). The most we can accept is ${mb} MB — try scanning it again at a lower quality, or split it into parts.`,
    );
  }

  if (file.size === 0) {
    return fail("This file is empty (0 bytes). It may not have finished saving — try choosing it again.");
  }

  if (!head || head.length === 0) {
    return fail("This file could not be read. Try choosing it again.");
  }

  const detected = sniffMime(head);
  if (!detected) {
    return fail(
      "This does not look like a PDF, PNG or JPEG — it may be a different kind of file, or it may be damaged. Please upload a PDF or a clear photo/scan.",
      null,
    );
  }

  return { ok: true, message: null, detectedMime: detected };
}

/** Human-readable byte size for the size-limit message. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
