import { useState } from "react";
import { createSimulationRun } from "../../api/endpoints";
import { formatClockTime, formatMinutes, toSafeNumber } from "../../core/format";
import { SCHEDULE_STATE_LABELS } from "../../core/statusLabels";
import { StatusBadge } from "../StatusBadge";
import { SCHEDULE_STATE_TONE } from "../statusTone";

export function SimulationPanel({ centreId }) {
  const [seed, setSeed] = useState(1);
  const [horizonMinutes, setHorizonMinutes] = useState(240);
  const [observationDelayMinutes, setObservationDelayMinutes] = useState(0);
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      setRun(await createSimulationRun({
        centreId,
        seed,
        horizonMinutes,
        resourceCount: 2,
        observationDelayMinutes,
      }));
    } catch {
      setError("Couldn't run the simulation. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const latestDecision = [...(run?.trace ?? [])]
    .reverse()
    .find((entry) => ["OBSERVE", "ESTIMATE", "ASSESS", "ADAPT"].includes(entry.action));
  const window = run?.completion_window;
  const observed = run?.observed_state;

  return (
    <section className="staff-panel" aria-label="Deterministic adaptive simulation">
      <div className="staff-panel__head">
        <div>
          <h2 className="screen__section-title">SIMULATION: Adaptive stress</h2>
          <p className="staff-panel__subtitle">
            Synthetic, deterministic operational data; live bookings are never changed.
          </p>
        </div>
      </div>

      <div className="simulation-controls">
        <label>
          Seed
          <input
            type="number"
            min="0"
            value={seed}
            onChange={(event) => setSeed(Number(event.target.value))}
          />
        </label>
        <label>
          Horizon (min)
          <input
            type="number"
            min="30"
            max="10080"
            value={horizonMinutes}
            onChange={(event) => setHorizonMinutes(Number(event.target.value))}
          />
        </label>
        <label>
          Observation delay
          <input
            type="number"
            min="0"
            max="10080"
            value={observationDelayMinutes}
            onChange={(event) => setObservationDelayMinutes(Number(event.target.value))}
          />
        </label>
        <button type="button" className="btn btn--secondary" onClick={handleRun} disabled={loading}>
          {loading ? "Running..." : "Run canonical scenario"}
        </button>
      </div>

      {error && <p className="form__error">{error}</p>}

      {!run ? (
        <p className="staff-panel__subtitle">
          Run the scenario to demonstrate NORMAL, disruption, stale observation, and recovery.
        </p>
      ) : (
        <>
          <div className="simulation-stage-list" aria-label="Simulation stages">
            {run.stages.map((stage, index) => (
              <span className="simulation-stage" key={`${stage.phase}-${index}`}>
                {stage.phase}
              </span>
            ))}
          </div>
          <p className="staff-panel__subtitle">
            Scenario stages: <strong>{run.canonical_stage_sequence}</strong>
          </p>

          <dl className="staff-stat-grid">
            <div className="staff-stat">
              <dt>Simulation clock</dt>
              <dd>{run.start_time}</dd>
              <p className="staff-stat__note">{run.scenario}</p>
            </div>
            <div className="staff-stat">
              <dt>Observed queue</dt>
              <dd>{observed?.queue_work ?? 0} lots</dd>
              <p className="staff-stat__note">{observed?.queue_quantity_kg ?? 0} kg</p>
            </div>
            <div className="staff-stat">
              <dt>Active servers</dt>
              <dd>{observed?.active_server_count ?? 0}</dd>
              <p className="staff-stat__note">
                {observed?.centre_status?.[`centre-${run.centre_id}`] ?? "Unknown"}
              </p>
            </div>
            <div className="staff-stat">
              <dt>Observation age</dt>
              <dd>{observed?.data_age_minutes ?? 0} min</dd>
              <p className="staff-stat__note">{observed?.is_stale ? "Stale" : "Fresh"}</p>
            </div>
            <div className="staff-stat">
              <dt>Completed work</dt>
              <dd>{run.adaptive_metrics?.completed ?? 0} lots</dd>
              <p className="staff-stat__note">
                {run.adaptive_metrics?.completed_quantity_kg ?? 0} kg
              </p>
            </div>
          </dl>
          <div className="simulation-detail-grid">
            <div>
              <h3>Stage queues</h3>
              <ul>
                {Object.entries(observed.stage_queues).map(([stage, value]) => (
                  <li key={stage}><strong>{stage}</strong>: {value.length} lots</li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Resources</h3>
              <ul>
                {Object.entries(observed.active_resources).map(([resource, value]) => (
                  <li key={resource}><strong>{resource}</strong>: {value.available ? (value.work_id ? "busy" : "available") : "outage"}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Canonical timeline</h3>
              <ol>
                {run.canonical_sequence.map((event, index) => (
                  <li key={`${event.at_minute ?? event.at}-${event.event_type}-${index}`}>
                    {event.at} — {event.event_type}
                  </li>
                ))}
              </ol>
            </div>
          </div>
          <p className="staff-panel__subtitle">
            Adaptive completion: {formatMinutes(toSafeNumber(run.adaptive_metrics?.completion_minutes))};
            baseline FIFO: {formatMinutes(toSafeNumber(run.baseline_metrics?.completion_minutes))}.
            {" "}This comparison is synthetic and does not alter live bookings.
          </p>
          <div className="simulation-metrics" aria-label="Baseline versus adaptive metrics">
            {Object.keys(run.adaptive_metrics ?? {}).filter((key) => typeof run.adaptive_metrics[key] !== "object").map((key) => (
              <div key={key}>
                <strong>{key.replaceAll("_", " ")}</strong>
                <span>Baseline: {run.baseline_metrics?.[key] ?? "—"}</span>
                <span>Adaptive: {run.adaptive_metrics?.[key] ?? "—"}</span>
                <span>Delta: {run.comparison?.metrics?.[key] ?? run.comparison?.[`${key}_delta`] ?? "—"}</span>
              </div>
            ))}
          </div>

          {latestDecision && (
            <div className="simulation-decision">
              <div className="simulation-decision__head">
                <strong>Latest decision</strong>
                <StatusBadge
                  label={SCHEDULE_STATE_LABELS[latestDecision.assessment] ?? latestDecision.assessment}
                  tone={SCHEDULE_STATE_TONE[latestDecision.assessment] ?? "neutral"}
                />
              </div>
              <p>{latestDecision.reason}</p>
              <p className="staff-panel__subtitle">
                Recommendation: {latestDecision.recommendation}
              </p>
              {window && (
                <>
                  <p className="staff-panel__subtitle">
                    Completion window: {formatClockTime(new Date(window.lower_timestamp))}–{" "}
                    {formatClockTime(new Date(window.upper_timestamp))} (
                    {window.claim}; uncertainty {formatMinutes(toSafeNumber(window.uncertainty_minutes))})
                  </p>
                  <p className="staff-panel__subtitle">
                    Observation captured {window.data_age_minutes ?? 0} min ago; confidence{" "}
                    {window.confidence ?? "unknown"}.
                  </p>
                </>
              )}
            </div>
          )}

          <details className="simulation-trace">
            <summary>View decision trace</summary>
            <ol>
              {run.trace
                .filter((entry) => ["OBSERVE", "ESTIMATE", "ASSESS", "ADAPT"].includes(entry.action))
                .map((entry, index) => (
                  <li key={`${entry.at}-${entry.action}-${index}`}>
                    <strong>{entry.action}</strong>
                    <span>
                      {entry.observed_at ?? entry.at}; queue {entry.observed_queue},{" "}
                      bottleneck {entry.bottleneck_stage ?? "—"}, servers {entry.active_server_count ?? 0},{" "}
                      age {entry.data_age_minutes} min; {entry.assessment} → {entry.recommendation}
                    </span>
                  </li>
                ))}
            </ol>
          </details>
        </>
      )}
      {centreId && <span className="sr-only">Centre {centreId}</span>}
    </section>
  );
}
