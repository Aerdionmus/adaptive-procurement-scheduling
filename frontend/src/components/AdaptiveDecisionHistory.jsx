import { EmptyState, ErrorState, LoadingState } from "./StateViews";
import { RECOMMENDATION_LABELS, SCHEDULE_STATE_LABELS } from "../core/statusLabels";

export function AdaptiveDecisionHistory({ data, loading, error, onRetry }) {
  if (loading) return <LoadingState label="Loading scheduling decisions…" />;
  if (error) return <ErrorState message="Scheduling history couldn't be loaded." onRetry={onRetry} />;
  if (data.length === 0) {
    return <EmptyState title="No scheduling decisions yet" message="Adaptive updates will appear here." />;
  }

  return (
    <section className="staff-panel" aria-label="Scheduling decisions">
      <h2 className="screen__section-title">Scheduling decisions</h2>
      <ul className="staff-affected-list">
        {data.map((decision) => (
          <li key={decision.id} className="staff-affected-item">
            <p className="staff-affected-item__recommendation">
              {SCHEDULE_STATE_LABELS[decision.scheduling_status] ?? "Scheduling update"} ·{" "}
              {RECOMMENDATION_LABELS[decision.recommendation] ?? "Recommendation available"}
            </p>
            <dl className="staff-affected-item__details">
              <div>
                <dt>Estimated completion</dt>
                <dd>{new Date(decision.estimated_completion_time).toLocaleString()}</dd>
              </div>
              <div>
                <dt>Wait estimate</dt>
                <dd>{decision.estimated_wait_minutes} min</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </section>
  );
}
