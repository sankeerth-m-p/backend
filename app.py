from dotenv import load_dotenv
load_dotenv()

import os
print("DEBUG DATABASE_URL =", os.getenv("DATABASE_URL"))

from flask import Flask
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

    from auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from events_routes import events_bp
    app.register_blueprint(events_bp, url_prefix="/events")

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
