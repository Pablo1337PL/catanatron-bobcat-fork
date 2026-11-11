import { useCallback, useContext, type FocusEvent } from "react";

import ACTIONS from "../actions";
import { store } from "../store";
import type { GameAction } from "../utils/api.types";

/**
 * Handlers that light up an action's place on the board while the pointer is
 * over an element or it has keyboard focus. On leaving, the highlight goes
 * back to `fallback` (e.g. a whole analysis move after one of its steps).
 */
export default function useHighlight() {
  const { dispatch } = useContext(store);
  return useCallback(
    (action: GameAction | null | undefined, fallback: GameAction | null = null) => {
      const set = (data: GameAction | null) => () =>
        dispatch({ type: ACTIONS.SET_HIGHLIGHT, data });
      // Focus events bubble in React: stop them, or a line step's focus would
      // be overridden by its move row. (Mouse enter/leave do not bubble.)
      const focus = (data: GameAction | null) => (event: FocusEvent) => {
        event.stopPropagation();
        set(data)();
      };
      return {
        onMouseEnter: set(action ?? null),
        onMouseLeave: set(fallback),
        onFocus: focus(action ?? null),
        onBlur: focus(fallback),
      };
    },
    [dispatch],
  );
}
