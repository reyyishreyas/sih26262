import { useCallback, useRef, useState } from "react";
import { checkUpload, type UploadCheck } from "./uploadCheck";

const SNIFF_BYTES = 8;

export interface FileCheckState {
  /** The currently chosen file, if any. */
  file: File | null;
  /** Live validation for the chosen file. null until something is chosen. */
  check: UploadCheck | null;
  /** True while the head bytes are being read. */
  reading: boolean;
  /** Set the chosen file and validate it immediately from its head bytes. */
  pick: (file: File | null) => void;
  /** Forget the chosen file (after a successful upload, or on reset). */
  clear: () => void;
}

/**
 * Choose-and-validate a file in one step.
 *
 * Only the first few bytes are read, so validation is effectively instant even
 * on a slow connection — the user sees "this PDF is password-protected" right
 * away instead of after a five-minute upload. The File object is kept whole for
 * the real upload; we never hold the whole file in memory just to check it.
 */
export function useFileCheck(): FileCheckState {
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<UploadCheck | null>(null);
  const [reading, setReading] = useState(false);
  // Guards against a stale read winning if the user picks a second file quickly.
  const requestId = useRef(0);

  const pick = useCallback((next: File | null) => {
    const id = requestId.current + 1;
    requestId.current = id;

    if (!next) {
      setFile(null);
      setCheck(null);
      setReading(false);
      return;
    }

    setFile(next);
    setReading(true);
    // Validate from the head bytes only — never wait for the whole file.
    void next
      .slice(0, SNIFF_BYTES)
      .arrayBuffer()
      .then((buffer) => {
        if (requestId.current !== id) return; // a newer choice already won
        setCheck(checkUpload(next, new Uint8Array(buffer)));
        setReading(false);
      })
      .catch(() => {
        if (requestId.current !== id) return;
        setCheck(checkUpload(next, null));
        setReading(false);
      });
  }, []);

  const clear = useCallback(() => {
    requestId.current += 1;
    setFile(null);
    setCheck(null);
    setReading(false);
  }, []);

  return { file, check, reading, pick, clear };
}
