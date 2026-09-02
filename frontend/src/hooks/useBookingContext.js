import { useCallback, useEffect, useState } from "react";
import { loadBookingContext } from "../core/bookingContext";

const INITIAL_STATE = { bookingId: null, status: "loading", data: null, error: null };

export function useBookingContext(bookingId, slotHint) {
  const [state, setState] = useState(INITIAL_STATE);

  const load = useCallback(() => {
    if (!bookingId) return;
    loadBookingContext(bookingId, { slotHint })
      .then((data) => setState({ bookingId, status: "ready", data, error: null }))
      .catch((error) => setState({ bookingId, status: "error", data: null, error }));
    // slotHint is intentionally excluded: it is only relevant on the first
    // load right after a booking is created, not on later reloads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId]);

  useEffect(() => {
    load();
  }, [load]);

  // Derive the externally-visible status from whether the last completed
  // fetch matches the bookingId we were asked for, rather than resetting to
  // "loading" with a synchronous setState inside the effect above.
  const isCurrent = state.bookingId === bookingId;

  return {
    status: isCurrent ? state.status : "loading",
    data: isCurrent ? state.data : null,
    error: isCurrent ? state.error : null,
    reload: load,
  };
}
