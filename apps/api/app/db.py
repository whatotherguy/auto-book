from sqlalchemy import inspect
from sqlmodel import SQLModel, Session, create_engine, select

from .config import settings
from .models import Issue, utc_now

engine = create_engine(settings.database_url, echo=False)


def migrate_issue_status_defaults(session: Session) -> None:
    open_issues = session.exec(select(Issue).where(Issue.status == "open")).all()
    if not open_issues:
        return

    migrated_at = utc_now()
    for issue in open_issues:
        issue.status = "approved"
        issue.updated_at = migrated_at
        session.add(issue)

    session.commit()


def init_db() -> None:
    if not inspect(engine).has_table("alembic_version"):
        # New schema changes must be made via Alembic migrations, not by modifying create_all directly.
        SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        migrate_issue_status_defaults(session)


def get_session():
    with Session(engine) as session:
        yield session
