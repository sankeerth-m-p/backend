from werkzeug.security import generate_password_hash
from app import app, db
from models import User


def upsert_user(username: str, password: str, role: str, email: str | None = None):
    user = User.query.filter_by(username=username).first()
    if user:
        user.password_hash = generate_password_hash(password)
        user.role = role
        if hasattr(user, "email"):
            user.email = email or user.email
        return user

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
    )
    if hasattr(user, "email"):
        user.email = email
    if hasattr(user, "auth_provider"):
        user.auth_provider = "email"
    if hasattr(user, "is_verified"):
        user.is_verified = True
    return user


with app.app_context():
    admin_user = upsert_user(
        username="mako_admin",
        password="123@mako",
        role="admin",
        email="mako_admin@example.com",
    )

    normal_user = upsert_user(
        username="mako_user",
        password="123@mako",
        role="user",
        email="mako_user@example.com",
    )

    db.session.add_all([admin_user, normal_user])
    db.session.commit()
    print("Seeded/updated admin and user accounts.")
