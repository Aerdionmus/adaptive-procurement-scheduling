from decimal import Decimal

from app.schemas.simulation import SimulationEvent, SimulationRunRequest
from app.services.simulation import run_simulation


def _request(**overrides):
    values = {"seed": 11, "horizon_minutes": 120, "centre_id": 1}
    values.update(overrides)
    return SimulationRunRequest(**values)


def test_seeded_runs_have_the_same_canonical_sequence_and_trace():
    first = run_simulation(_request())
    second = run_simulation(_request())
    assert first["canonical_sequence"] == second["canonical_sequence"]
    assert first["trace"] == second["trace"]


def test_outage_delays_work_and_recovery_reopens_centre():
    events = [
        SimulationEvent(event_type="arrival", at_minute=0, service_minutes=10),
        SimulationEvent(event_type="outage", at_minute=1),
        SimulationEvent(event_type="arrival", at_minute=2, service_minutes=10),
        SimulationEvent(event_type="recovery", at_minute=30),
    ]
    result = run_simulation(_request(events=events, horizon_minutes=40))
    actions = [item["action"] for item in result["trace"]]
    assert "outage" in actions and "recovery" in actions
    assert result["true_state"]["centre_status"]["centre-1"] == "OPEN"
    assert result["adaptive_metrics"]["completed"] == 2


def test_stale_observation_widens_completion_window():
    fresh = run_simulation(_request(observation_interval_minutes=5, stale_after_minutes=20))
    stale = run_simulation(_request(observation_interval_minutes=60, stale_after_minutes=20))
    assert stale["completion_window"]["is_stale"]
    assert stale["completion_window"]["uncertainty_minutes"] > fresh["completion_window"]["uncertainty_minutes"]


def test_true_state_and_observed_state_are_distinct():
    result = run_simulation(_request(observation_interval_minutes=60))
    assert "queue_work" in result["true_state"]
    assert result["observed_state"]["observed_at"]
    assert result["observed_state"]["data_age_minutes"] >= 0
    assert result["true_state"]["at"] != result["observed_state"]["captured_at"]


def test_baseline_metrics_are_present_for_comparison():
    result = run_simulation(_request())
    assert result["baseline_metrics"]["policy"] == "static FIFO, one resource"
    assert "completion_delta_minutes" in result["comparison"]


def test_resource_specific_outage_is_recovered_without_closing_centre():
    events = [
        SimulationEvent(event_type="arrival", at_minute=0, service_minutes=14),
        SimulationEvent(
            event_type="outage",
            at_minute=1,
            resource_type="quality",
            resource_id="quality-1",
        ),
        SimulationEvent(
            event_type="recovery",
            at_minute=30,
            resource_type="quality",
            resource_id="quality-1",
        ),
    ]
    result = run_simulation(_request(events=events, horizon_minutes=60))
    assert result["true_state"]["centre_status"]["centre-1"] == "OPEN"
    assert any(item["action"] == "outage" and item["resource_id"] == "quality-1" for item in result["trace"])
    assert result["adaptive_metrics"]["completed"] == 1


def test_no_show_is_counted_without_creating_work():
    result = run_simulation(
        _request(
            events=[SimulationEvent(event_type="no_show", at_minute=0)],
            horizon_minutes=30,
        )
    )
    assert result["adaptive_metrics"]["arrival_statuses"]["no-show"] == 1
    assert result["adaptive_metrics"]["admitted"] == 0


def test_adaptive_stress_is_a_replayable_real_timeline():
    result = run_simulation(_request(scenario="adaptive_stress", horizon_minutes=120))
    assert result["scenario"] == "adaptive_stress"
    assert "T09:00:00+00:00" in result["canonical_sequence"][0]["at"]
    assert {event["event_type"] for event in result["canonical_sequence"]} >= {
        "arrival", "no_show", "outage", "recovery"
    }
    assert result["adaptive_metrics"]["no_shows"] == 1
    assert result["adaptive_metrics"]["peak_queue"] > 0


def test_adaptive_and_baseline_metrics_have_operational_deltas():
    result = run_simulation(_request())
    for key in ("throughput_kg_per_hour", "mean_wait_minutes", "peak_queue"):
        assert key in result["adaptive_metrics"]
        assert key in result["baseline_metrics"]
    assert "throughput_delta_kg" in result["comparison"]
    decisions = [item for item in result["trace"] if item["action"] in {"OBSERVE", "ESTIMATE", "ASSESS", "ADAPT"}]
    assert decisions and all(item["policy"] == "canonical-adaptive-v1" for item in decisions)


def test_adaptive_stress_disruptions_change_assessment_and_recommendation():
    result = run_simulation(_request(scenario="adaptive_stress", horizon_minutes=240))
    decisions = [
        item for item in result["trace"]
        if item["action"] == "ASSESS"
    ]
    assert any(item["assessment"] == "AT_RISK" for item in decisions)
    assert any(
        item["assessment"] == "DELAYED"
        and item["recommendation"] == "PROPOSE_NEW_SLOT"
        for item in decisions
    )
    assert {item["policy"] for item in decisions} == {"canonical-adaptive-v1"}
    assert all(item["policy_thresholds_minutes"] == {"at_risk": 10, "delayed": 45} for item in decisions)
    assert result["adaptive_metrics"]["completion_within_slot_pct"] < 100


def test_adaptive_stress_response_is_caused_by_resource_disruptions():
    arrivals = [
        SimulationEvent(
            event_type="arrival",
            at_minute=20 + index * 10,
            quantity_kg=Decimal("50"),
            service_minutes=60,
            scheduled_minute=20 + index * 10,
        )
        for index in range(5)
    ]
    clean = run_simulation(_request(events=arrivals, horizon_minutes=240))
    disrupted = run_simulation(
        _request(
            events=arrivals + [
                SimulationEvent(
                    event_type="outage",
                    at_minute=75,
                    resource_type="quality",
                    resource_id="quality-1",
                ),
                SimulationEvent(
                    event_type="outage",
                    at_minute=105,
                    resource_type="weighment",
                    resource_id="weighment-1",
                ),
            ],
            horizon_minutes=240,
        )
    )
    clean_assessments = {
        item["assessment"] for item in clean["trace"] if item["action"] == "ASSESS"
    }
    disrupted_assessments = {
        item["assessment"] for item in disrupted["trace"] if item["action"] == "ASSESS"
    }
    assert "DELAYED" not in clean_assessments
    assert "DELAYED" in disrupted_assessments
    assert (
        disrupted["adaptive_metrics"]["completion_within_slot_pct"]
        < clean["adaptive_metrics"]["completion_within_slot_pct"]
    )


def test_baseline_metrics_are_derived_from_serial_fifo_timeline():
    result = run_simulation(_request(scenario="adaptive_stress", horizon_minutes=240))
    baseline = result["baseline_metrics"]
    assert baseline["completion_within_slot_pct"] == round(
        100 * (baseline["admitted"] - baseline["delayed_lots"]) / baseline["admitted"],
        2,
    )
    assert baseline["mean_cycle_minutes"] > baseline["mean_wait_minutes"]
    assert baseline["time_integrated_resource_utilisation_minutes"] == baseline["completion_minutes"]
    assert baseline["peak_queue"] > 0
