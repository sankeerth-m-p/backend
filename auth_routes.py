from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from flask_jwt_extended import create_access_token
from models import User
from extensions import db

ADMIN_PASSWORD = "password123" 
auth_bp = Blueprint("auth", __name__)
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json

    user = User.query.filter_by(username=data["username"]).first()

    if not user or not check_password_hash(user.password_hash, data["password"]):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(identity=str(user.id)) 

    return jsonify({
        "token": token,
        "username": user.username
    })
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    admin_password = data.get("admin_password", "")
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    # admin auth
    if admin_password != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 403

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    user = User(
        username=username,
        password_hash=generate_password_hash(password)
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({
        "message": "User created successfully",
        "username": username
    }), 201
