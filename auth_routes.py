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
import re

auth_bp = Blueprint("auth", __name__)


def make_tokens(user_id: int):
    user = User.query.get(int(user_id))
    uid = str(user_id)
    role = (user.role or "").lower() if user else ""
    return {
        "token": create_access_token(identity=uid, additional_claims={"role": role}),
        "refreshToken": create_refresh_token(identity=uid, additional_claims={"role": role}),
    }


def user_payload(user: User):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "displayName": user.display_name,
        "avatarUrl": user.avatar_url,
        "authProvider": user.auth_provider,
    }


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    selected_role = (data.get("role") or "").strip().lower()

    if not username or not password or not selected_role:
        return jsonify({"error": "username, password and role are required"}), 400

    if selected_role not in {"user", "admin"}:
        return jsonify({"error": "role must be either 'user' or 'admin'"}), 400

    user = (
        User.query.filter_by(username=username).first()
        or User.query.filter_by(email=username).first()
    )

    if not user or not user.password_hash:
        return jsonify({"error": "Invalid credentials"}), 401

    if not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    actual_role = (user.role or "").lower()
    if actual_role not in {"user", "admin"}:
        return jsonify({"error": "Account role is invalid. Contact admin."}), 403
    if actual_role != selected_role:
        return jsonify({"error": "Selected role does not match this account"}), 403

    return jsonify({**make_tokens(user.id), **user_payload(user)}), 200


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}

    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()
    confirm_password = (
        data.get("confirm_password")
        or data.get("confirm")
        or data.get("confirmPassword")
        or ""
    )
    confirm_password = str(confirm_password).strip()
    phone_number = (data.get("phone_number") or "").strip() or None
    role = (data.get("role") or "").strip().lower()

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if not confirm_password:
        return jsonify({"error": "confirm password is required"}), 400
    if password != confirm_password:
        return jsonify({"error": "password and confirm_password must match"}), 400

    if not role:
        return jsonify({"error": "role is required"}), 400
    if role not in {"user", "admin"}:
        return jsonify({"error": "role must be either 'user' or 'admin'"}), 400

    if not email:
        email = username

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        phone_number=phone_number,
        role=role,
        auth_provider="email",
        is_verified=True,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "message": "User created successfully",
        "username": username,
        "role": role,
    }), 201


@auth_bp.route("/google", methods=["POST"])
def google_auth():
    data = request.get_json() or {}
    credential = (data.get("credential") or "").strip()
    selected_role = (data.get("role") or "").strip().lower()
    mode = (data.get("mode") or "").strip().lower()

    if not credential:
        return jsonify({"error": "Missing Google credential"}), 400
    if not selected_role:
        return jsonify({"error": "role is required"}), 400
    if selected_role not in {"user", "admin"}:
        return jsonify({"error": "role must be either 'user' or 'admin'"}), 400
    if mode and mode not in {"login", "register"}:
        return jsonify({"error": "mode must be either 'login' or 'register'"}), 400

    try:
        google_user = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            Config.GOOGLE_CLIENT_ID,
        )
    except ValueError as e:
        return jsonify({"error": f"Invalid Google token: {str(e)}"}), 401

    google_id = google_user.get("sub")
    email = google_user.get("email", "")
    display_name = google_user.get("name", "")
    avatar_url = google_user.get("picture", "")
    is_verified = google_user.get("email_verified", False)

    if not google_id:
        return jsonify({"error": "Could not extract Google user ID"}), 400

    user = User.query.filter_by(google_id=google_id).first()
    if not user and email:
        user = User.query.filter_by(email=email).first()

    if user:
        actual_role = (user.role or "").lower()
        if actual_role not in {"user", "admin"}:
            return jsonify({"error": "Account role is invalid. Contact admin."}), 403
        if actual_role != selected_role:
            return jsonify({"error": "Selected role does not match this account"}), 403
        if mode == "register":
            return jsonify({"error": "Account already exists"}), 409

        if not user.google_id:
            user.google_id = google_id
            user.auth_provider = "google"
        user.avatar_url = avatar_url or user.avatar_url
        db.session.commit()
    else:
        if mode == "login":
            return jsonify({"error": "Account not found. Please register first."}), 404

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
            role=selected_role,
            auth_provider="google",
            is_verified=is_verified,
        )
        db.session.add(user)
        db.session.commit()

    return jsonify({**make_tokens(user.id), **user_payload(user)}), 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({**make_tokens(user.id), **user_payload(user)}), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user_payload(user)), 200
