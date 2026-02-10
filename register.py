from werkzeug.security import generate_password_hash
from app import app, db
from models import User

with app.app_context():
    mako = User(
        username="mako",
        password_hash=generate_password_hash("123@mako")
    )

    db.session.add_all([mako])
    db.session.commit()
