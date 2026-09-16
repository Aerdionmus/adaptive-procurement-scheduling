from datetime import datetime, timedelta, timezone

from app.schemas.prediction import ServiceTimePrediction
from app.services.completion_window import adapt_completion_window
from app.services.scheduling import (
    SchedulingRecommendation,
    SchedulingStatus,
    classify_completion,
    recommend_for_status,
)


AT = datetime(2026, 9, 16, 4, tzinfo=timezone.utc)


def legacy_window() -> dict:
    return {
        "earliest_minutes": 20.0,
        "latest_minutes": 35.0,
        "lower_timestamp": "2026-09-16T04:20:00+00:00",
        "upper_timestamp": "2026-09-16T04:35:00+00:00",
        "p50_timestamp": "2026-09-16T04:23:45+00:00",
        "p90_timestamp": "2026-09-16T04:31:15+00:00",
        "uncertainty_minutes": 15.0,
        "confidence": "medium",
        "baseline_service_minutes": 10.0,
        "workload_delay_minutes": 10.0,
    }


def prediction(*, confidence: str = "MEDIUM", status: str = "READY") -> ServiceTimePrediction:
    return ServiceTimePrediction(
        centre_id=1,
        target="total_active_service",
        predicted_minutes=25.0,
        p50_minutes=25.0,
        p90_minutes=40.0,
        status=status,
        confidence=confidence,
        sample_count=10,
        method="RECENT_MEDIAN",
        fallback_level="CENTRE_OVERALL",
        lookback_start=AT,
        lookback_end=AT,
        source="OPERATIONAL_TELEMETRY",
        reference_context_used=[],
    )


def test_unavailable_insufficient_low_and_stale_use_legacy_estimator():
    for candidate, stale in (
        (None, False),
        (prediction(status="INSUFFICIENT_DATA"), False),
        (prediction(confidence="LOW"), False),
        (prediction(), True),
    ):
        result = adapt_completion_window(
            legacy_window(),
            at=AT,
            prediction=candidate,
            prediction_stale=stale,
        )
        assert result["provenance"] == "LEGACY_ESTIMATOR"
        assert result["earliest_minutes"] == 20.0
        assert result["latest_minutes"] == 35.0
        assert result["lower_timestamp"] == "2026-09-16T04:20:00+00:00"
        assert result["upper_timestamp"] == "2026-09-16T04:35:00+00:00"
        assert result["uncertainty_minutes"] == 15.0


def test_valid_prediction_uses_p50_central_and_p90_upper_bound():
    result = adapt_completion_window(legacy_window(), at=AT, prediction=prediction())
    assert result["provenance"] == "PREDICTIVE_CALIBRATION"
    assert result["earliest_minutes"] == 35.0
    assert result["latest_minutes"] == 50.0
    assert result["uncertainty_minutes"] == 15.0
    assert result["workload_delay_minutes"] == 10.0
    assert result["prediction_adjusted_service_minutes"] == 25.0
    assert result["p50_timestamp"] == "2026-09-16T04:35:00+00:00"
    assert result["p90_timestamp"] == "2026-09-16T04:50:00+00:00"
    assert result["prediction_sample_count"] == 10


def test_high_confidence_output_is_deterministic_and_does_not_classify():
    first = adapt_completion_window(legacy_window(), at=AT, prediction=prediction(confidence="HIGH"))
    second = adapt_completion_window(legacy_window(), at=AT, prediction=prediction(confidence="HIGH"))
    assert first == second
    assert "assessment" not in first
    assert "recommendation" not in first


def test_shorter_prediction_reduces_only_service_component():
    result = adapt_completion_window(
        legacy_window(),
        at=AT,
        prediction=prediction(),
    )
    assert result["workload_delay_minutes"] == 10.0
    assert result["earliest_minutes"] == 35.0


def test_upper_bound_never_narrows_when_prediction_is_shorter():
    shorter = prediction()
    shorter.p50_minutes = 5.0
    shorter.p90_minutes = 8.0
    result = adapt_completion_window(legacy_window(), at=AT, prediction=shorter)
    assert result["earliest_minutes"] == 15.0
    assert result["latest_minutes"] == 35.0


def test_policy_thresholds_and_recommendations_remain_unchanged():
    assert classify_completion(
        AT + timedelta(minutes=10),
        AT,
    ) == SchedulingStatus.ON_TRACK
    assert classify_completion(
        AT + timedelta(minutes=10, seconds=1),
        AT,
    ) == SchedulingStatus.AT_RISK
    assert classify_completion(
        AT + timedelta(minutes=45, seconds=1),
        AT,
    ) == SchedulingStatus.DELAYED
    recommendation, slot_id, centre_id = recommend_for_status(SchedulingStatus.AT_RISK)
    assert recommendation == SchedulingRecommendation.WARN_FARMER
    assert slot_id is None
    assert centre_id is None
