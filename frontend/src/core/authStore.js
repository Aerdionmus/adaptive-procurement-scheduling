// Session storage for the JWT issued by POST /api/auth/login (or
// immediately after POST /api/auth/register - see Onboarding.jsx).
//
// The backend enforces JWT bearer auth + RBAC on every booking, queue,
// scheduling, and admin/throughput endpoint (see backend/app/api/deps.py).
// This module - together with the Authorization header attached in
// api/client.js - is what makes the frontend able to actually call those
// endpoints instead of getting 401s on every request.
//
// Kept deliberately tiny and framework-free (plain localStorage, like
// core/storage.js's existing farmer/booking-id persistence) rather than a
// new state-management dependency.

const AUTH_KEY = "aps.auth";

/**
 * @typedef {Object} AuthSession
 * @property {string} token
 * @property {"FARMER"|"CENTRE_STAFF"|"ADMIN"} role
 * @property {string} email
 * @property {number|null} farmerId
 * @property {number|null} centreId
 */

/** @returns {AuthSession|null} */
export function getAuthSession() {
  try {
    const raw = window.localStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/** @param {AuthSession} session */
export function setAuthSession(session) {
  window.localStorage.setItem(AUTH_KEY, JSON.stringify(session));
}

export function clearAuthSession() {
  window.localStorage.removeItem(AUTH_KEY);
}

export function getAuthToken() {
  return getAuthSession()?.token ?? null;
}
