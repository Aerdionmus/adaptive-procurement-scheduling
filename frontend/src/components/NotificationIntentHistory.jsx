import { EmptyState, ErrorState, LoadingState } from "./StateViews";
import {
  NOTIFICATION_CHANNEL_LABELS,
  NOTIFICATION_STATUS_LABELS,
  NOTIFICATION_TYPE_LABELS,
} from "../core/statusLabels";

export function NotificationIntentHistory({ data, loading, error, onRetry }) {
  if (loading) return <LoadingState label="Loading notification history…" />;
  if (error) return <ErrorState message="Notification history couldn't be loaded." onRetry={onRetry} />;
  if (data.length === 0) {
    return <EmptyState title="No notifications yet" message="Adaptive notifications will appear here." />;
  }

  return (
    <section className="staff-panel" aria-label="Notification history">
      <h2 className="screen__section-title">Notification history</h2>
      <ul className="staff-affected-list">
        {data.map((intent) => (
          <li key={intent.id} className="staff-affected-item">
            <p className="staff-affected-item__recommendation">
              {NOTIFICATION_TYPE_LABELS[intent.notification_type] ?? "Notification"}
            </p>
            <dl className="staff-affected-item__details">
              <div>
                <dt>Status</dt>
                <dd>{NOTIFICATION_STATUS_LABELS[intent.status] ?? intent.status}</dd>
              </div>
              <div>
                <dt>Channel</dt>
                <dd>{NOTIFICATION_CHANNEL_LABELS[intent.channel] ?? intent.channel}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{new Date(intent.created_at).toLocaleString()}</dd>
              </div>
              {intent.failure_reason && (
                <div>
                  <dt>Failure reason</dt>
                  <dd>{intent.failure_reason}</dd>
                </div>
              )}
              {intent.provider_reference && (
                <div>
                  <dt>Reference</dt>
                  <dd>{intent.provider_reference}</dd>
                </div>
              )}
            </dl>
          </li>
        ))}
      </ul>
    </section>
  );
}
