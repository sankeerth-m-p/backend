from extensions import db
from sqlalchemy import inspect, text


EVENTS_REMINDER_COLUMNS = {
    "event_datetime": "TIMESTAMP NULL",
    "reminder_minutes_before": "INTEGER NULL",
    "reminder_at": "TIMESTAMP NULL",
    "reminder_timezone": "VARCHAR(64) NULL",
    "notification_status": "VARCHAR(20) NULL",
    "notification_sent_at": "TIMESTAMP NULL",
}


def migrate_events_table():
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    if "events" not in tables:
        return

    existing_columns = {col["name"] for col in inspector.get_columns("events")}

    for column_name, ddl in EVENTS_REMINDER_COLUMNS.items():
        if column_name in existing_columns:
            continue

        db.session.execute(text(f"ALTER TABLE events ADD COLUMN {column_name} {ddl}"))

    db.session.commit()
