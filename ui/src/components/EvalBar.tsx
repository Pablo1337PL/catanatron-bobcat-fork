import type { Color } from "../utils/api.types";

export function percent(probability: number | undefined) {
  return `${((probability ?? 0) * 100).toFixed(1)}%`;
}

/** Two-color (or more) bar of win probabilities, like a chess evaluation bar. */
export default function EvalBar({
  colors,
  winProbability,
  compact = false,
}: {
  colors: Color[];
  winProbability: Partial<Record<Color, number>>;
  compact?: boolean;
}) {
  return (
    <div
      className={`eval-bar${compact ? " compact" : ""}`}
      role="img"
      aria-label={colors
        .map((color) => `${color} ${percent(winProbability[color])}`)
        .join(", ")}
    >
      {colors.map((color) => {
        const p = winProbability[color] ?? 0;
        return (
          <div
            key={color}
            className={`eval-segment ${color.toLowerCase()}`}
            style={{ flexGrow: p, flexBasis: 0 }}
          >
            {!compact && p >= 0.12 && (
              <span>
                {color} {percent(p)}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
