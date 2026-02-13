from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import Event
from datetime import datetime
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
    for r in rows:
        date_iso = r.date.isoformat()
        result.setdefault(date_iso, {})[f"Event {r.event_col}"] = r.value

    return jsonify(result), 200


@events_bp.route("/cell", methods=["POST"])
@jwt_required()
def update_cell():
    user_id = get_jwt_identity()
    data = request.json

    if not data:
        return jsonify({"error": "Missing body"}), 400

    event = Event.query.filter_by(
        user_id=user_id,
        date=data["dateISO"],
        event_col=data["eventCol"],
    ).first()

    if event:
        event.value = data["value"]
    else:
        event = Event(
            user_id=user_id,
            date=data["dateISO"],
            event_col=data["eventCol"],
            value=data["value"],
        )
        db.session.add(event)

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

        # extra safety: only apply to selected month
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
                db.session.add(Event(
                    user_id=user_id,
                    date=date_obj,
                    event_col=event_col,
                    value=value
                ))

    db.session.commit()
    return jsonify({"ok": True})
