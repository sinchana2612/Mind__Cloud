import logging
import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv(Path(__file__).with_name(".env"))


def get_db():
    """Return a MySQL connection configured from the environment."""
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "counselling_system"),
        autocommit=False,
    )


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me"),
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", str(Path(__file__).with_name("uploads"))),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    if app.config["SECRET_KEY"] == "dev-only-change-me":
        app.logger.warning("FLASK_SECRET_KEY is not configured; use a unique secret in production.")

    from routes.admin import admin
    from routes.auth import auth
    from routes.student import student
    from routes.teacher import teacher

    app.register_blueprint(auth)
    app.register_blueprint(admin)
    app.register_blueprint(student)
    app.register_blueprint(teacher)

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("login.html", error="Page not found."), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception("Unhandled application error: %s", error)
        return render_template("login.html", error="An unexpected error occurred. Please try again."), 500

    return app


app = create_app()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
