from sqlalchemy import event, inspect
from sqlmodel import SQLModel, Session, create_engine, select

from .config import settings
from .models import Issue, utc_now

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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
        from .jobs import recover_orphaned_jobs
        recover_orphaned_jobs(session)


def get_session():
    with Session(engine) as session:
        yield session
