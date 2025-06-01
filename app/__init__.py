# app/__init__.py
import os
import logging
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_cors import CORS
from config import Config
# import stripe # Moved stripe init inside create_app

# Initialize extensions at the module level
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True) # Ensures instance folder is relative to app root
    app.config.from_object(config_class)

    # Configure logging early
    if not app.debug and not app.testing:
        # Logging setup for production (can be more elaborate)
        app.logger.setLevel(logging.INFO)
        # Example: add a file handler
        # from logging.handlers import RotatingFileHandler
        # file_handler = RotatingFileHandler('logs/leadforge.log', maxBytes=10240, backupCount=10)
        # file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        # app.logger.addHandler(file_handler)
    else:
        app.logger.setLevel(logging.DEBUG)

    app.logger.info("LeadForge Backend Initializing...")
    app.logger.debug(f"Debug mode: {app.debug}")
    app.logger.debug(f"Instance path: {app.instance_path}")

    # --- CRITICAL FOR SQLITE & MIGRATIONS ---
    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        # Using print for immediate visibility during CLI commands like flask db migrate
        print(f"DEBUG [create_app]: Ensured instance path exists: {app.instance_path}")
    except OSError as e:
        print(f"ERROR [create_app]: Could not create instance path {app.instance_path}: {e}")
        # Depending on your needs, you might want to raise the error or exit
    # --- END CRITICAL SECTION ---

    # Print the database URI being used by the app for debugging
    # Using print for immediate visibility during CLI commands
    print(f"DEBUG [create_app]: SQLALCHEMY_DATABASE_URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    if 'sqlite:///' in app.config.get('SQLALCHEMY_DATABASE_URI', '') and 'instance' not in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
        print(f"WARNING [create_app]: SQLALCHEMY_DATABASE_URI for SQLite does not seem to be in the instance folder: {app.config.get('SQLALCHEMY_DATABASE_URI')}")


    # Stripe initialization (if you have stripe keys in config)
    # if app.config.get('STRIPE_SECRET_KEY'):
    #     import stripe
    #     stripe.api_key = app.config['STRIPE_SECRET_KEY']
    #     app.logger.info("Stripe API key configured for app instance.")
    # else:
    #     app.logger.warning("STRIPE_SECRET_KEY not set. Stripe functionality will be unavailable.")

    # Initialize Flask extensions with the app instance
    db.init_app(app)
    migrate.init_app(app, db) # Pass both app and db
    login_manager.init_app(app)
    
    CORS(app, supports_credentials=True, origins=[
        app.config.get('FRONTEND_URL', 'http://localhost:3000'),
        "http://localhost:5173", # LeadForge Pro frontend dev port
        # Add any other origins as needed
    ])
    
    app.logger.info(f"CORS configured for origins: {app.config.get('FRONTEND_URL', 'http://localhost:3000')}, http://localhost:5175")

    # Import and register Blueprints
    # It's good practice to do this within an app_context if blueprints might access app config or extensions during import
    # However, for simple blueprint definitions, direct registration is also common.
    # The `with app.app_context()` you had is fine, but not strictly necessary if blueprints only define routes.
    from .routes_auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth') # Added common url_prefix

    from .routes_leads import leads_bp
    app.register_blueprint(leads_bp, url_prefix='/leads') # Added common url_prefix

    from .routes_search import search_bp
    app.register_blueprint(search_bp, url_prefix='/api/search') # Added common url_prefix
    
    # If you add payment_routes.py later:
    # from .payment_routes import payments_bp
    # app.register_blueprint(payments_bp, url_prefix='/api/payments')

    @app.route('/health') # Changed from '/' to '/health' for a common health check endpoint
    def health_check():
        app.logger.debug("Health check path /health accessed")
        return jsonify(message="LeadForge Backend Operational", status="OK", version="0.0.1")

    # --- CRITICAL FOR ALEMBIC/FLASK-MIGRATE ---
    # Import models AFTER db is defined and initialized with the app,
    # and BEFORE Alembic's env.py tries to access db.metadata.
    # This ensures that when env.py imports your app (or parts of it to get metadata),
    # the models are already defined and associated with the 'db' instance.
    from . import models
    app.logger.debug("Models imported.")
    # --- END CRITICAL SECTION ---

    app.logger.info("LeadForge Backend Initialized Successfully.")
    return app

# Note: The `from app import models` was originally at the very bottom.
# Moving it into `create_app` before returning `app` is a common pattern that also works
# and ensures models are known to the app instance returned by the factory.
# The key is that `models` is imported so that `db.metadata` is populated before
# Alembic's `env.py` needs it. If `env.py` imports your `create_app` and calls it,
# then `models` being imported within `create_app` before `migrate.init_app`
# or having `env.py` import `app.models` directly after getting the `db` object
# from the app context are both valid approaches.
# Keeping `from . import models` at the end of `create_app` before `return app`
# is a robust way to ensure they are loaded into the app's context correctly.