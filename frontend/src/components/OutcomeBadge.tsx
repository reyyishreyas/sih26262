import type { Outcome } from "../types";
import { outcomeIcon, plainOutcome } from "../labels";
import { Icon } from "./Icon";

/** Plain-language pill for a compliance result. Colour + icon + word. */
export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  return (
    <span
      className={`pill outcome-${outcome.toLowerCase()}`}
      title={outcome.replaceAll("_", " ")}
    >
      <Icon name={outcomeIcon(outcome)} size={14} />
      {plainOutcome(outcome)}
    </span>
  );
}
