import { useState } from "react";
import { BookingSummary } from "../components/BookingSummary";
import { ETAIndicator } from "../components/ETAIndicator";
import { QueueStatus } from "../components/QueueStatus";
import { SchedulingAlert } from "../components/SchedulingAlert";
import { StatusTimeline } from "../components/StatusTimeline";
import { ErrorState, LoadingState } from "../components/StateViews";
import { checkIn } from "../api/endpoints";
import { useBookingContext } from "../hooks/useBookingContext";
import { useSchedulingStatus } from "../hooks/useSchedulingStatus";
import { navigate } from "../core/router";

export function TrackProcurement({ bookingId }) {
  const { status, data, reload } = useBookingContext(bookingId);
  const { status: scheduleStatus, loading: scheduleLoading } = useSchedulingStatus(
    status === "ready" ? data : null,
  );
  const [checkingIn, setCheckingIn] = useState(false);
  const [checkInError, setCheckInError] = useState(null);

  async function handleCheckIn() {
    setCheckingIn(true);
    setCheckInError(null);
    try {
      await checkIn({ bookingId: data.booking.id, centreId: data.booking.centre_id });
      reload();
    } catch {
      setCheckInError("We couldn't check you in. Please try again.");
    } finally {
      setCheckingIn(false);
    }
  }

  function handleReviewRecommendation(recommendation) {
    if (recommendation.type === "PROPOSE_NEW_SLOT") {
      navigate(
        `/book?centreId=${data.centre.id}&slotId=${recommendation.slot.id}`,
      );
    } else if (recommendation.type === "RECOMMEND_ALTERNATE_CENTRE") {
      navigate(
        `/book?centreId=${recommendation.centre.id}&slotId=${recommendation.slot.id}`,
      );
    }
  }

  if (status === "loading") {
    return <LoadingState label="Loading your procurement status\u2026" />;
  }

  if (status === "error") {
    return (
      <ErrorState
        message="We couldn't load your procurement status. Please try again."
        onRetry={reload}
      />
    );
  }

  const { booking, slot, centre, queueEntry, eta } = data;

  return (
    <div className="screen">
      <BookingSummary booking={booking} slot={slot} centre={centre} compact />

      <StatusTimeline bookingStatus={booking.status} queueStatus={queueEntry?.queue_status} />

      {booking.status === "BOOKED" && (
        <div className="check-in-panel">
          <p>Arrived at the centre? Check in to join the live queue.</p>
          <button
            type="button"
            className="btn btn--primary btn--block"
            onClick={handleCheckIn}
            disabled={checkingIn}
          >
            {checkingIn ? "Checking in\u2026" : "Check in at centre"}
          </button>
          {checkInError && <p className="form__error">{checkInError}</p>}
        </div>
      )}

      {queueEntry && (
        <QueueStatus
          queueEntry={queueEntry}
          centreCode={centre?.code}
          farmersAhead={eta?.farmers_ahead ?? 0}
        />
      )}

      {eta && (
        <ETAIndicator
          estimatedWaitMinutes={eta.estimated_wait_minutes}
          estimatedCompletion={queueEntry ? eta.estimatedCompletionAt : null}
        />
      )}

      {!scheduleLoading && scheduleStatus && (
        <SchedulingAlert status={scheduleStatus} onReviewRecommendation={handleReviewRecommendation} />
      )}
    </div>
  );
}
