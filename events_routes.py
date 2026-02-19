from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models import Event


events_bp = Blueprint("events", __name__)


@events_bp.route("/month", methods=["GET"])
@jwt_required()
def get_month_events():
    user_id = get_jwt_identity()

    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)

    if not year or not month:
        return jsonify({"error": "year and month are required"}), 400

    rows = Event.query.filter(
        Event.user_id == user_id,
        db.extract("year", Event.date) == year,
        db.extract("month", Event.date) == month,
    ).all()

    result = {}
    for row in rows:
        date_iso = row.date.isoformat()
        result.setdefault(date_iso, {})[f"Event {row.event_col}"] = row.value

    return jsonify(result), 200


@events_bp.route("/cell", methods=["POST"])
@jwt_required()
def update_cell():
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    date_iso = data.get("dateISO")
    event_col = data.get("eventCol")
    value = data.get("value")

    if not date_iso or event_col is None or value is None:
        return jsonify({"error": "dateISO, eventCol and value are required"}), 400

    try:
        event_col = int(event_col)
    except (TypeError, ValueError):
        return jsonify({"error": "eventCol must be a number"}), 400

    try:
        date_obj = datetime.strptime(date_iso, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid dateISO format. Use YYYY-MM-DD"}), 400

    event = Event.query.filter_by(
        user_id=user_id,
        date=date_obj,
        event_col=event_col,
    ).first()

    if not event:
        event = Event(user_id=user_id, date=date_obj, event_col=event_col, value="")
        db.session.add(event)

    event.value = value

    event_datetime_raw = data.get("eventDateTime")
    reminder_minutes_before = data.get("reminderMinutesBefore")
    reminder_at_raw = data.get("reminderAt")
    reminder_timezone = data.get("reminderTimezone")
    notification_status = data.get("notificationStatus")

    event.event_datetime = _parse_iso_datetime(event_datetime_raw)
    event.reminder_at = _parse_iso_datetime(reminder_at_raw)
    event.reminder_minutes_before = (
        int(reminder_minutes_before)
        if reminder_minutes_before not in (None, "")
        else None
    )
    event.reminder_timezone = reminder_timezone or None
    event.notification_status = notification_status or None

    db.session.commit()
    return jsonify({"ok": True}), 200


@events_bp.route("/month", methods=["DELETE"])
@jwt_required()
def clear_month():
    user_id = get_jwt_identity()

    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)

    if not year or not month:
        return jsonify({"error": "year and month are required"}), 400

    Event.query.filter(
        Event.user_id == user_id,
        db.extract("year", Event.date) == year,
        db.extract("month", Event.date) == month,
    ).delete(synchronize_session=False)

    db.session.commit()
    return jsonify({"ok": True}), 200

@events_bp.route("/delete-bulk", methods=["POST"])
@jwt_required()
def bulk_delete_events():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    items = data.get("items", [])

    if not isinstance(items, list):
        return jsonify({"error": "items must be a list"}), 400

    deleted = 0

    for item in items:
        if not isinstance(item, dict):
            continue

        date_iso = item.get("dateISO")
        event_col_raw = item.get("eventCol")

        if not date_iso or event_col_raw is None:
            continue

        try:
            date_obj = datetime.strptime(date_iso, "%Y-%m-%d").date()
            event_col = int(event_col_raw)
        except (ValueError, TypeError):
            continue

        if event_col <= 0:
            continue

        event = Event.query.filter_by(
            user_id=user_id,
            date=date_obj,
            event_col=event_col,
        ).first()

        if event:
            db.session.delete(event)
            deleted += 1

    db.session.commit()
    return jsonify({"ok": True, "deleted": deleted}), 200

@events_bp.route("/bulk", methods=["POST"])
@jwt_required()
def bulk_upsert_events():
    user_id = get_jwt_identity()
    data = request.get_json()

    year = data.get("year")
    month = data.get("month")
    rows = data.get("rows", [])

    if not year or not month or not isinstance(rows, list):
        return jsonify({"error": "Invalid payload"}), 400

    for row in rows:
        date_iso = row.get("dateISO")
        events = row.get("events", {})

        if not date_iso or not isinstance(events, dict):
            continue

        try:
            date_obj = datetime.strptime(date_iso, "%Y-%m-%d").date()
        except ValueError:
            continue

        if date_obj.year != year or date_obj.month != month:
            continue

        for key, value in events.items():
            if not value or not key.startswith("Event "):
                continue

            event_col = int(key.replace("Event ", ""))

            existing = Event.query.filter_by(
                user_id=user_id,
                date=date_obj,
                event_col=event_col,
            ).first()

            if existing:
                existing.value = value
            else:
                db.session.add(
                    Event(
                        user_id=user_id,
                        date=date_obj,
                        event_col=event_col,
                        value=value,
                    )
                )

    db.session.commit()
    return jsonify({"ok": True})


def _parse_iso_datetime(raw):
    if raw in (None, ""):
        return None

    if isinstance(raw, str):
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    return None
