// Combines several existing endpoints into the one bundle every screen
// actually needs to render a booking: the booking itself, its centre and
// slot, and - if the farmer has checked in - their live queue entry + ETA.
//
// NOTE ON A BACKEND GAP: there is no GET /api/centres/{id} (single) or
// GET /api/queue/bookings/{booking_id} endpoint today, only
// GET /api/centres/ (list) and GET /api/queue/centres/{centre_id} (live
// queue for a centre). This loader works around both by fetching the list
// and filtering client-side, which is fine at demo scale but is exactly
// the kind of thing a real GET /api/farmers/{id}/bookings +
// GET /api/bookings/{id}/queue-entry pair would simplify. Flagged in the
// final report rather than changed here, since backend changes are out of
// scope for this workstream.
import { getBooking, getLiveQueue, getQueueEta, listCentres, listCentreSlots } from "../api/endpoints";

const LIVE_QUEUE_BOOKING_STATUSES = new Set(["CHECKED_IN", "IN_QUEUE", "PROCESSING"]);

/**
 * @param {number} bookingId
 * @param {object} [options]
 * @param {object} [options.slotHint] - a slot object already known on the
 *   client (e.g. the one the farmer just picked in the booking flow), used
 *   instead of a fresh lookup. Needed because a slot that has since filled
 *   up (capacity reaches 0) is excluded from the "usable slots" endpoint.
 */
export async function loadBookingContext(bookingId, { slotHint } = {}) {
  const booking = await getBooking(bookingId);
  const centres = await listCentres();
  const centre = centres.find((c) => c.id === booking.centre_id) ?? null;

  let slot = slotHint && slotHint.id === booking.slot_id ? slotHint : null;
  if (!slot && centre) {
    try {
      const slots = await listCentreSlots(centre.id);
      slot = slots.find((s) => s.id === booking.slot_id) ?? null;
    } catch {
      slot = null;
    }
  }

  let queueEntry = null;
  let eta = null;
  if (centre && LIVE_QUEUE_BOOKING_STATUSES.has(booking.status)) {
    try {
      const liveQueue = await getLiveQueue(centre.id);
      queueEntry = liveQueue.find((entry) => entry.booking_id === booking.id) ?? null;
      if (queueEntry) {
        eta = await getQueueEta(queueEntry.id).catch(() => null);
        if (eta) {
          // Computed once, here, at fetch time - not during render - so
          // components can read a stable timestamp instead of calling
          // Date.now() themselves on every render.
          eta.estimatedCompletionAt = new Date(
            Date.now() + Number(eta.estimated_wait_minutes) * 60000,
          );
        }
      }
    } catch {
      queueEntry = null;
    }
  }

  return { booking, centre, slot, queueEntry, eta };
}
