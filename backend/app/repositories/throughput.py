from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ThroughputSnapshot


def get_latest_snapshot(session: Session, centre_id: int) -> ThroughputSnapshot | None:
    """Return the most recent throughput snapshot for a centre, if any."""
    return session.scalar(
        select(ThroughputSnapshot)
        .where(ThroughputSnapshot.centre_id == centre_id)
        .order_by(ThroughputSnapshot.snapshot_at.desc(), ThroughputSnapshot.id.desc())
        .limit(1)
    )
