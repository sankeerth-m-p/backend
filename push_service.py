from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from pywebpush import WebPushException, webpush

from extensions import db
from models import Event, PushSubscription


scheduler: BackgroundScheduler | None = None


def start_push_scheduler(app):
    global scheduler
    if scheduler is not None:
        return

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        lambda: _safe_process_due_reminders(app),
        trigger="interval",
        seconds=30,
        id="push-reminder-dispatcher",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()


def _safe_process_due_reminders(app):
    with app.app_context():
        try:
            process_due_reminders()
        except Exception as exc:
            print(f"[push] reminder loop failed: {exc}")


def process_due_reminders(batch_size: int = 100):
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    due_events = (
        Event.query.filter(
            Event.notification_status == "pending",
            Event.reminder_at.isnot(None),
            Event.reminder_at <= now_utc_naive,
        )
        .order_by(Event.reminder_at.asc())
        .limit(batch_size)
        .all()
    )

    if not due_events:
        return

    vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    vapid_public_key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    vapid_sub = os.getenv("VAPID_CLAIMS_SUB", "mailto:admin@example.com").strip()

    if not vapid_private_key or not vapid_public_key:
        for event in due_events:
            event.notification_status = "failed"
        db.session.commit()
        print("[push] missing VAPID keys, marked due reminders as failed")
        return

    for event in due_events:
        subs = PushSubscription.query.filter_by(user_id=event.user_id).all()
        if not subs:
            event.notification_status = "failed"
            continue

        payload = json.dumps(
            {
                "title": "Event Reminder",
                "body": event.value or "You have an upcoming event.",
                "dateISO": event.date.isoformat(),
                "eventCol": event.event_col,
            }
        )

        any_success = False
        for sub in subs:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims={"sub": vapid_sub},
                )
                any_success = True
            except WebPushException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code in (404, 410):
                    db.session.delete(sub)
                else:
                    print(f"[push] failed for subscription {sub.id}: {exc}")
            except Exception as exc:
                print(f"[push] unexpected push error for subscription {sub.id}: {exc}")

        event.notification_status = "sent" if any_success else "failed"
        if any_success:
            event.notification_sent_at = now_utc_naive

    db.session.commit()
