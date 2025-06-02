# app/__init__.py
import os
import logging
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_cors import CORS
from config import Config

# Initialize extensions at the module level
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # --- Logging Setup ---
    if not app.debug and not app.testing:
        app.logger.setLevel(logging.INFO)
    else:
        app.logger.setLevel(logging.DEBUG)
    app.logger.info("LeadForge Backend Initializing...")
    app.logger.debug(f"Debug mode: {app.debug}")
    app.logger.debug(f"Instance path: {app.instance_path}")

    # --- Instance Path and DB URI Debug ---
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        print(f"DEBUG [create_app]: Ensured instance path exists: {app.instance_path}")
    except OSError as e:
        print(f"ERROR [create_app]: Could not create instance path {app.instance_path}: {e}")
    db_uri_print = app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
    print(f"DEBUG [create_app]: SQLALCHEMY_DATABASE_URI: {db_uri_print}")

    # --- Initialize Flask Extensions (SQLAlchemy, Migrate first) ---
    db.init_app(app)
    migrate.init_app(app, db)
    
    # --- Flask-Login Configuration ---
    login_manager.init_app(app)
    login_manager.login_view = 'auth_bp.login' # Assumes blueprint in routes_auth.py is named 'auth_bp'
    login_manager.session_protection = "strong"

    # Import models before user_loader and blueprints that use models
    from . import models 
    app.logger.debug("Models imported for create_app context.")

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))
    # --- End Flask-Login Configuration ---

    # --- CORS Configuration - MORE ROBUST ---
    # Ensure this is configured BEFORE blueprints that need CORS are registered,
    # or at least that Flask-CORS correctly handles app-level config for blueprints.
    # Placing it before blueprint registration is generally safer.
    frontend_url = app.config.get('FRONTEND_URL', 'http://localhost:5173') # Get it once
    CORS(
        app,
        origins=[frontend_url, "http://localhost:5173"], # Ensure current dev port is explicitly listed
                                                           # Redundant if FRONTEND_URL is correctly set in .env
        supports_credentials=True,
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], # Allow all common methods
        allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-CSRFToken"] # Common headers
        # Add "Cookie" to allow_headers if you ever need to inspect it directly, though withCredentials handles sending it.
    )
    app.logger.info(f"CORS configured robustly. Allowing origin: {frontend_url}. Methods: GET,POST,PUT,DELETE,OPTIONS. Headers: Content-Type, etc.")
    # --- END CORS Configuration ---

    # --- Import and Register Blueprints ---
    from .routes_auth import auth_bp # Assuming the blueprint instance is named auth_bp in routes_auth.py
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .routes_leads import leads_bp
    app.register_blueprint(leads_bp, url_prefix='/api/leads')

    from .routes_search import search_bp
    app.register_blueprint(search_bp, url_prefix='/api/search')

    # --- Health Check Route ---
    @app.route('/health')
    def health_check():
        app.logger.debug("Health check path /health accessed")
        return jsonify(message="LeadForge Backend Operational", status="OK", version="0.0.1")
    
    app.logger.info("LeadForge Backend Initialized Successfully.")
    return app