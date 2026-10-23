"""Human-readable identifier generation, safe under concurrent requests.

Each counter is a row in ``id_sequences`` incremented with a single atomic
``UPDATE ... RETURNING`` inside the caller's transaction. The database write lock
serialises concurrent writers, and unique constraints on the code columns are a
final safeguard. Counting existing rows is never used.
"""

from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import IdSequence


def next_value(session: Session, name: str) -> int:
    session.execute(
        sqlite_insert(IdSequence).values(name=name, last_value=0).on_conflict_do_nothing(index_elements=["name"])
    )
    return session.execute(
        update(IdSequence)
        .where(IdSequence.name == name)
        .values(last_value=IdSequence.last_value + 1)
        .returning(IdSequence.last_value)
    ).scalar_one()


def next_institution_code(session: Session) -> str:
    return f"INST-{next_value(session, 'institution'):05d}"


def next_application_code(session: Session, academic_year: str) -> str:
    year = academic_year[:4]
    return f"REG-EoA-{year}-{next_value(session, f'application:{year}'):04d}"
