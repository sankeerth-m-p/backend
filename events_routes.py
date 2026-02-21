from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import Event, User
from datetime import datetime, date
from whatsapp_service import send_whatsapp
import re
events_bp = Blueprint("events", __name__)

TAG_PREFIX_RE = re.compile(r"^\s*__TAG:([A-Za-z0-9_-]+)__\s*(.*)$")
LEGACY_LABEL_RE = re.compile(r"^\s*__([A-Za-z0-9_-]+)__\s*(.*)$")
BRACKET_LABEL_RE = re.compile(r"^\s*\[([A-Za-z0-9_-]+)\]\s*(.*)$")
COLOR_RE = re.compile(r"^\s*\{(#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}))\}\s*(.*)$")


def parse_tagged_event_value(raw_value):
    """
    Parses frontend encoded event value into label/text/color.
    Supported:
    - __TAG:LABEL_ID__ {#RRGGBB} Event title
    - __TAG:LABEL_ID__ Event title
    - {#RRGGBB} Event title
    - Event title
    Legacy:
    - __LABEL__ ...
    - [LABEL] ...
    """
    s = (raw_value or "").strip()
    label_id = None
    text_color = None

    m = TAG_PREFIX_RE.match(s) or LEGACY_LABEL_RE.match(s) or BRACKET_LABEL_RE.match(s)
    if m:
        label_id = m.group(1)
        s = m.group(2).strip()

    c = COLOR_RE.match(s)
    if c:
        text_color = c.group(1)
        s = c.group(2).strip()

    return {
        "label_id": label_id,
        "text_color": text_color,
        "text": s,
    }


def build_today_user_events_payload(target_date=None):
    """
    Build a list of users with today's events.
    Output shape:
    [
      {
        "user_id": 1,
        "username": "alice",
        "phone_number": "whatsapp:+91...",
        "events": [{"event_col": 1, "value": "Meeting"}]
      }
    ]
    """
    if target_date is None:
        target_date = date.today()

    rows = (
        db.session.query(User, Event)
        .join(Event, Event.user_id == User.id)
        .filter(Event.date == target_date)
        .order_by(User.id.asc(), Event.event_col.asc())
        .all()
    )

    by_user = {}
    for user, event in rows:
        parsed_value = parse_tagged_event_value(event.value)

        if user.id not in by_user:
            by_user[user.id] = {
                "user_id": user.id,
                "username": user.username,
                "phone_number": user.phone_number,
                "events": [],
            }

        by_user[user.id]["events"].append(
            {
                "event_col": event.event_col,
                "value": event.value,
                "description": event.description,
                "label": parsed_value.get("label_id"),
                "text_color": parsed_value.get("text_color"),
                "name": parsed_value.get("text"),
                "date": event.date.isoformat(),
            }
        )

    return list(by_user.values())


def build_whatsapp_message(username, target_date, events):
    total = len(events)
    lines = [
        "Upcoming Events",
        f"Date: {target_date.isoformat()}",
        f"User: {username}",
        f"Total Events: {total}",
        "",
    ]

    for idx, event in enumerate(events, start=1):
        name = (event.get("name") or "").strip() or "Untitled Event"
        description = (event.get("description") or "").strip() or "No description"
        label = (event.get("label") or "").strip() or "General"
        color = (event.get("text_color") or "").strip() or "None"

        lines.append(f"Event {idx}")
        lines.append(f"Name: {name}")
        lines.append(f"Description: {description}")
        lines.append(f"Label: {label}")
        # lines.append(f"Color: {color}")
        lines.append("")

    return "\n".join(lines).strip()


def execute_whatsapp_for_date(target_date):
    users = build_today_user_events_payload(target_date=target_date)
    results = []

    for user in users:
        phone = (user.get("phone_number") or "").strip()
        if not phone:
            results.append(
                {
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "phone_number": None,
                    "sent": False,
                    "error": "Missing phone_number",
                }
            )
            continue

        if not phone.startswith("whatsapp:"):
            phone = f"whatsapp:{phone}"

        message = build_whatsapp_message(
            username=user["username"],
            target_date=target_date,
            events=user["events"],
        )

        try:
            send_result = send_whatsapp(phone, message)
            results.append(
                {
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "phone_number": phone,
                    "sent": True,
                    "sid": send_result.get("sid"),
                    "status": send_result.get("status"),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "phone_number": phone,
                    "sent": False,
                    "error": str(exc),
                }
            )

    sent_count = sum(1 for r in results if r["sent"])
    return {
        "date": target_date.isoformat(),
        "total_users_with_events": len(users),
        "sent_count": sent_count,
        "failed_count": len(results) - sent_count,
        "results": results,
    }

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
        date_bucket = result.setdefault(date_iso, {})
        event_key = f"Event {r.event_col}"
        date_bucket[event_key] = r.value
        date_bucket.setdefault("_descriptions", {})[event_key] = r.description

    return jsonify(result), 200


@events_bp.route("/cell", methods=["POST"])
@jwt_required()
def update_cell():
    user_id = get_jwt_identity()
    data = request.json

    if not data:
        return jsonify({"error": "Missing body"}), 400

    date_iso = data.get("dateISO")
    event_col = data.get("eventCol")
    value = data.get("value")

    if date_iso is None or event_col is None or value is None:
        return jsonify({"error": "dateISO, eventCol, value are required"}), 400

    event = Event.query.filter_by(
        user_id=user_id,
        date=date_iso,
        event_col=event_col,
    ).first()

    if event:
        event.value = value
        if "description" in data:
            event.description = (data.get("description") or "").strip()
    else:
        event = Event(
            user_id=user_id,
            date=date_iso,
            event_col=event_col,
            value=value,
            description=(data.get("description") or "").strip(),
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

        for key, raw_event in events.items():
            if not key.startswith("Event "):
                continue

            try:
                event_col = int(key.replace("Event ", ""))
            except ValueError:
                continue

            # Backward compatible:
            # - old payload: "Event 1": "Title"
            # - new payload: "Event 1": {"value": "Title", "description": "..."}
            if isinstance(raw_event, dict):
                value = (raw_event.get("value") or "").strip()
                description = (raw_event.get("description") or "").strip()
            else:
                value = (str(raw_event) if raw_event is not None else "").strip()
                description = ""

            if not value:
                continue

            existing = Event.query.filter_by(
                user_id=user_id,
                date=date_obj,
                event_col=event_col,
            ).first()

            if existing:
                existing.value = value
                existing.description = description
            else:
                db.session.add(Event(
                    user_id=user_id,
                    date=date_obj,
                    event_col=event_col,
                    value=value,
                    description=description,
                ))

    db.session.commit()
    return jsonify({"ok": True})


@events_bp.route("/today-user-events", methods=["GET"])
def today_user_events():
    """
    Returns a list of users and their event list for today.
    Optional query param:
      - date=YYYY-MM-DD (for testing)
    """
    date_str = request.args.get("date", "").strip()
    target_date = date.today()

    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD"}), 400

    payload = build_today_user_events_payload(target_date=target_date)
    return jsonify(
        {
            "date": target_date.isoformat(),
            "count": len(payload),
            "users": payload,
        }
    ), 200


@events_bp.route("/trigger-whatsapp-today", methods=["POST"])
def trigger_whatsapp_today():
    """
    Trigger WhatsApp messages for all users who have events today and a phone number.
    Optional query param:
      - date=YYYY-MM-DD (for testing)
    """
    date_str = request.args.get("date", "").strip()
    target_date = date.today()

    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD"}), 400

    summary = execute_whatsapp_for_date(target_date=target_date)
    return jsonify(summary), 200
