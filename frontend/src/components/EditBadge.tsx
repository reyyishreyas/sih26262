export function EditBadge({
  extraction,
  claim,
}: {
  extraction: unknown;
  claim: unknown | null;
}) {
  if (claim === null || claim === undefined || String(claim) === String(extraction)) {
    return null;
  }

  return (
    <span
      className="pill warn edit-badge"
      title="The institution claim differs from the extracted value. Rules continue to use the extracted value."
    >
      Edited after extraction
    </span>
  );
}
