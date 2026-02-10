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

    __table_args__ = (
        db.UniqueConstraint("user_id", "date", "event_col"),
    )