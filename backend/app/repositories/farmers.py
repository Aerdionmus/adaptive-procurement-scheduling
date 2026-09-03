from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Farmer
from app.schemas.procurement import FarmerCreate


def create_farmer(session: Session, farmer_data: FarmerCreate) -> Farmer:
    farmer = Farmer(**farmer_data.model_dump())
    session.add(farmer)
    session.commit()
    session.refresh(farmer)
    return farmer


def list_farmers(session: Session) -> list[Farmer]:
    return list(session.scalars(select(Farmer).order_by(Farmer.id)))


def get_farmer(session: Session, farmer_id: int) -> Farmer | None:
    return session.get(Farmer, farmer_id)
