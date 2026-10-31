"""Database tables (D-3, D-4, D-5.1, D-7, D-15). Times are ISO 8601 UTC strings, as in the contract."""

from sqlalchemy import JSON, Boolean, Index, Integer, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Integration(Base):
    """D-15: the only source of truth for configs. One row per integration, edited in place."""

    __tablename__ = "integrations"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    config: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class _Record:
    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    fetched_at: Mapped[str] = mapped_column(String(32))
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class User(_Record, Base):
    __tablename__ = "users"
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_login: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Device(_Record, Base):
    __tablename__ = "devices"
    hostname: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    os: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Alert(_Record, Base):
    __tablename__ = "alerts"
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    timestamp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


RECORD_TABLES = {"user": User, "device": Device, "alert": Alert}


class Quarantine(Base):
    __tablename__ = "quarantine"
    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))
    target_schema: Mapped[str] = mapped_column(String(16))
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    raw: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(32))


class Run(Base):
    __tablename__ = "runs"
    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    integration: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    trigger: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[str] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_pulled: Mapped[int] = mapped_column(Integer, default=0)
    records_valid: Mapped[int] = mapped_column(Integer, default=0)
    records_invalid: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        # D-10: only one run of an action can be running at a time, which also makes a second worker safe
        Index("one_running_run_per_action", "integration", "action", unique=True,
              postgresql_where=text("status = 'running'"), sqlite_where=text("status = 'running'")),
    )

    @property
    def run_id(self) -> str:
        return f"run-{self.pk}"


class Secret(Base):
    """D-7.1, D-7.6: an encrypted value and the one host it may be sent to."""

    __tablename__ = "secrets"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[str] = mapped_column(String(32))


class ActionState(Base):
    """Values the engine keeps between runs ({{state.x}}), such as last_success_at for incremental sync (B-1)."""

    __tablename__ = "action_state"
    integration: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_success_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class PathBaseline(Base):
    """Mapped paths seen in earlier successful runs of an action, for the schema drift check.
    A new table, so an existing database gets it from create_all without altering anything."""

    __tablename__ = "path_baseline"
    integration: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(64), primary_key=True)
    paths: Mapped[list] = mapped_column(JSON, default=list)


class AlertAttempt(Base):
    """The last time an alert email was due for an action, and what came of it, so the dashboard can say whether the person
    was told. One row per action; it is removed when the action next succeeds (the streak, and so the alert, resets)."""

    __tablename__ = "alert_attempt"
    integration: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(64), primary_key=True)
    at: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))  # sent, failed, not_configured
    failures: Mapped[int] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(String(240), nullable=True)
