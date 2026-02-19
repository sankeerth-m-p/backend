from dotenv import load_dotenv
load_dotenv()

import os
print("DEBUG DATABASE_URL =", os.getenv("DATABASE_URL"))

from flask import Flask
from flask_cors import CORS
from config import Config
from extensions import db, jwt
from db_migrations import migrate_events_table, migrate_push_subscriptions_table
from push_service import start_push_scheduler
import models  # noqa: F401


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)
    jwt.init_app(app)

    with app.app_context():
        db.create_all()
        migrate_events_table()
        migrate_push_subscriptions_table()

    # temp: init-db route (remove after first use)
    @app.route("/init-db")
    def init_db():
        with app.app_context():
            db.create_all()
            migrate_events_table()
            migrate_push_subscriptions_table()
        return "DB initialized"

    from auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from events_routes import events_bp
    app.register_blueprint(events_bp, url_prefix="/events")
    from push_routes import push_bp
    app.register_blueprint(push_bp, url_prefix="/push")

    should_start_scheduler = not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if should_start_scheduler:
        start_push_scheduler(app)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
