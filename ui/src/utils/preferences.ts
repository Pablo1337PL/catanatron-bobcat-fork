/**
 * Per-browser display preferences. Storage can be missing or throw (private
 * windows, blocked site data), so every read and write falls back quietly.
 */

const SHOW_LABELS_KEY = "catanatron.showTileLabels";

/** Whether the board shows the tile letters A-S; on unless turned off. */
export function loadShowLabels(): boolean {
  try {
    return window.localStorage.getItem(SHOW_LABELS_KEY) !== "false";
  } catch {
    return true;
  }
}

export function saveShowLabels(show: boolean): void {
  try {
    window.localStorage.setItem(SHOW_LABELS_KEY, String(show));
  } catch {
    // Not remembered; the toggle still works for this page.
  }
}
