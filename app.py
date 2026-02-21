from dotenv import load_dotenv
load_dotenv()

import os
print("DEBUG DATABASE_URL =", os.getenv("DATABASE_URL"))

from datetime import datetime, date
from flask import Flask, jsonify, request
from flask_cors import CORS
from config import Config
from extensions import db, jwt

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)
    jwt.init_app(app)

    # ✅ TEMP: init-db route (remove after first use)
    @app.route("/init-db")
    def init_db():
        with app.app_context():
            db.create_all()
        return "DB initialized"

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"ok": True}), 200

    from auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from events_routes import events_bp, execute_whatsapp_for_date
    app.register_blueprint(events_bp, url_prefix="/events")

    @app.route("/cron/trigger-whatsapp", methods=["GET", "POST"])
    def cron_trigger_whatsapp():
        cron_secret = os.getenv("CRON_SECRET", "").strip()
        provided_secret = (
            request.headers.get("X-Cron-Secret", "").strip()
            or request.args.get("secret", "").strip()
        )

        if cron_secret and provided_secret != cron_secret:
            return jsonify({"error": "Unauthorized"}), 401

        date_str = request.args.get("date", "").strip()
        target_date = date.today()
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"error": "date must be YYYY-MM-DD"}), 400

        summary = execute_whatsapp_for_date(target_date=target_date)
        return jsonify(summary), 200

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
