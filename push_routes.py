from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models import PushSubscription
import os


push_bp = Blueprint("push", __name__)


@push_bp.route("/public-key", methods=["GET"])
def get_public_key():
    public_key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    if not public_key:
        return jsonify({"error": "VAPID_PUBLIC_KEY is not configured"}), 500
    return jsonify({"publicKey": public_key}), 200


@push_bp.route("/subscribe", methods=["POST"])
@jwt_required()
def subscribe():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    endpoint = data.get("endpoint")
    keys = data.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    expiration_time = data.get("expirationTime")
    user_agent = request.headers.get("User-Agent")

    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "Invalid subscription payload"}), 400

    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not sub:
        sub = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            expiration_time=expiration_time,
            user_agent=user_agent,
        )
        db.session.add(sub)
    else:
        sub.user_id = user_id
        sub.p256dh = p256dh
        sub.auth = auth
        sub.expiration_time = expiration_time
        sub.user_agent = user_agent

    db.session.commit()
    return jsonify({"ok": True}), 200


@push_bp.route("/unsubscribe", methods=["POST"])
@jwt_required()
def unsubscribe():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    endpoint = data.get("endpoint")

    if not endpoint:
        return jsonify({"error": "endpoint is required"}), 400

    deleted = PushSubscription.query.filter_by(user_id=user_id, endpoint=endpoint).delete()
    db.session.commit()
    return jsonify({"ok": True, "deleted": deleted}), 200
