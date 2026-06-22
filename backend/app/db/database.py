from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{settings.db_path}",
    # write transactions stay open across LLM awaits (~10s) — wait instead of failing
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _migrate() -> None:
    """Additive SQLite migrations — keeps existing demo data when columns are added."""
    new_columns = {
        "anchor_mappings": [
            ("evidence_strength", "TEXT DEFAULT 'medium'"),
            ("decision_impact", "TEXT DEFAULT 'medium'"),
            ("temporal_status", "TEXT DEFAULT 'active'"),
        ],
        "concepts": [
            ("status", "TEXT DEFAULT 'observed'"),
            ("origin", "TEXT DEFAULT '[]'"),
            ("version", "FLOAT DEFAULT 1.0"),
            ("scenario_scope", "TEXT DEFAULT '[]'"),
            ("user_visible_label", "TEXT"),
            ("sme_translation", "TEXT DEFAULT '[]'"),
        ],
        "preference_state_snapshots": [
            ("stage", "TEXT"),
            ("anchor_breakdown", "TEXT DEFAULT '{}'"),
            ("motivation_scores", "TEXT DEFAULT '{}'"),
        ],
        "participants": [
            ("spec_markdown", "TEXT"),
            ("spec_version", "INTEGER DEFAULT 0"),
            ("updated_at", "TIMESTAMP"),
            ("survey", "TEXT DEFAULT '{}'"),
        ],
        "intention_relations": [
            ("verification", "TEXT DEFAULT 'unverified'"),
            ("plausibility", "FLOAT"),
            ("causal_evidence", "TEXT"),
        ],
        "products": [
            ("tags", "TEXT DEFAULT '[]'"),
        ],
    }
    # 컬럼 이름 변경 (renames) — (table, old, new). 이미 new가 있으면 skip(재실행 안전).
    # 2026-06-22: intent_labels → dialogue_acts (화행; IntentionTopic 가치와 혼동 해소).
    renames = [
        ("turns", "intent_labels", "dialogue_acts"),
    ]
    with engine.connect() as conn:
        for table, columns in new_columns.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not existing:
                continue  # table will be created by create_all
            for name, ddl in columns:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        for table, old, new in renames:
            cols = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not cols:
                continue  # table will be created by create_all (already new name)
            if old in cols and new not in cols:
                conn.exec_driver_sql(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
        conn.commit()


def init_db() -> None:
    # Import models so they register on Base.metadata before create_all.
    from app.db import models  # noqa: F401

    _migrate()
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
