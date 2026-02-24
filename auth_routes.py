from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from models import User
from extensions import db
from config import Config
import re, os

auth_bp = Blueprint("auth", __name__)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password123")

# ── helpers ──────────────────────────────────────────────────

def make_tokens(user_id: int):
    uid = str(user_id)
    return {
        "token":        create_access_token(identity=uid),
        "refreshToken": create_refresh_token(identity=uid),
    }

def user_payload(user: User):
    return {
        "id":           user.id,
        "username":     user.username,
        "email":        user.email,
        "displayName":  user.display_name,
        "avatarUrl":    user.avatar_url,
        "authProvider": user.auth_provider,
    }

def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))

# ── existing login (keep working for old users) ───────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    # support login by username OR email
    user = (
        User.query.filter_by(username=username).first()
        or User.query.filter_by(email=username).first()
    )

    if not user or not user.password_hash:
        return jsonify({"error": "Invalid credentials"}), 401

    if not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({**make_tokens(user.id), **user_payload(user)}), 200

# ── existing register (keep working) ─────────────────────────

# @auth_bp.route("/register", methods=["POST"])
# def register():
    data = request.get_json() or {}

    admin_password = data.get("admin_password", "")
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if admin_password != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 403

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        auth_provider="email",
        is_verified=True,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "message": "User created successfully",
        "username": username
    }), 201
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}

    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()
    phone_number = (data.get("phone_number") or "").strip() or None

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if not email:
        email = username  # username is email in new flow

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        phone_number=phone_number,
        auth_provider="email",
        is_verified=True,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "message": "User created successfully",
        "username": username
    }), 201
# ── Google OAuth ──────────────────────────────────────────────

@auth_bp.route("/google", methods=["POST"])
def google_auth():
    data = request.get_json() or {}
    credential = (data.get("credential") or "").strip()  # Google ID token

    if not credential:
        return jsonify({"error": "Missing Google credential"}), 400

    # Verify the token with Google
    try:
        google_user = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            Config.GOOGLE_CLIENT_ID,
        )
    except ValueError as e:
        return jsonify({"error": f"Invalid Google token: {str(e)}"}), 401

    google_id    = google_user.get("sub")          # unique google user id
    email        = google_user.get("email", "")
    display_name = google_user.get("name", "")
    avatar_url   = google_user.get("picture", "")
    is_verified  = google_user.get("email_verified", False)

    if not google_id:
        return jsonify({"error": "Could not extract Google user ID"}), 400

    # 1. Find by google_id (returning google user)
    user = User.query.filter_by(google_id=google_id).first()

    # 2. Find by email (user registered with email before, link accounts)
    if not user and email:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id    = google_id
            user.auth_provider = "google"
            user.avatar_url   = avatar_url or user.avatar_url
            db.session.commit()

    # 3. New user — create account
    if not user:
        # auto-generate a username from display name
        base = re.sub(r"[^a-z0-9]", "_", display_name.lower())[:20] or "user"
        username = base
        suffix = 1
        while User.query.filter_by(username=username).first():
            username = f"{base}_{suffix}"
            suffix += 1

        user = User(
            username=username,
            email=email,
            google_id=google_id,
            display_name=display_name,
            avatar_url=avatar_url,
            auth_provider="google",
            is_verified=is_verified,
        )
        db.session.add(user)
        db.session.commit()

    return jsonify({**make_tokens(user.id), **user_payload(user)}), 200

# ── Refresh token ─────────────────────────────────────────────

@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({**make_tokens(user.id), **user_payload(user)}), 200

# ── Me (get current user info) ────────────────────────────────

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user_payload(user)), 200