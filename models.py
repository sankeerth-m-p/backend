from extensions import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, nullable=False)
    event_col = db.Column(db.Integer, nullable=False)
    value = db.Column(db.Text, nullable=False)

    # reminder/notification fields
    event_datetime = db.Column(db.DateTime, nullable=True)
    reminder_minutes_before = db.Column(db.Integer, nullable=True)
    reminder_at = db.Column(db.DateTime, nullable=True)
    reminder_timezone = db.Column(db.String(64), nullable=True)
    notification_status = db.Column(db.String(20), nullable=True)
    notification_sent_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("user_id", "date", "event_col"),
    )


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.Text, nullable=False)
    expiration_time = db.Column(db.BigInteger, nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )
