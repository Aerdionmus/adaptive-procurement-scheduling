// Thin, named wrappers around the shared API client (client.js).
// Screens and hooks call these instead of building URL strings inline, so
// the request shape for each backend resource lives in exactly one place.
import { getJson, postJson } from "./client";

// ---- Farmers ---------------------------------------------------------

export function createFarmer({ name, phone, village }) {
  return postJson("/api/farmers/", { name, phone, village });
}

export function listFarmers() {
  return getJson("/api/farmers/");
}

// ---- Procurement centres & slots --------------------------------------

export function listCentres() {
  return getJson("/api/centres/");
}

export function listCentreSlots(centreId) {
  return getJson(`/api/centres/${centreId}/slots`);
}

// ---- Bookings ----------------------------------------------------------

export function createBooking({ farmerId, centreId, slotId, cropType, quantityKg }) {
  return postJson("/api/bookings/", {
    farmer_id: farmerId,
    centre_id: centreId,
    slot_id: slotId,
    crop_type: cropType,
    quantity_kg: quantityKg,
  });
}

export function getBooking(bookingId) {
  return getJson(`/api/bookings/${bookingId}`);
}

// ---- Queue & ETA ---------------------------------------------------------

export function checkIn({ bookingId, centreId }) {
  return postJson("/api/queue/check-in", { booking_id: bookingId, centre_id: centreId });
}

export function getLiveQueue(centreId) {
  return getJson(`/api/queue/centres/${centreId}`);
}

export function getQueueEta(queueEntryId) {
  return getJson(`/api/queue/${queueEntryId}/eta`);
}

// ---- Phase 3 adaptive scheduling ------------------------------------
// Live as of backend commit f54202e. See core/schedulingAdapter.js for the
// response contract and how the frontend consumes it.

export function getBookingSchedule(bookingId) {
  return getJson(`/api/scheduling/bookings/${bookingId}`);
}

export function getCentreSchedule(centreId) {
  return getJson(`/api/scheduling/centres/${centreId}`);
}
