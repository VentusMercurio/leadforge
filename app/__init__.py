# app/__init__.py
import os
import logging
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_cors import CORS
from config import Config
from flask_caching import Cache 

# --- Initialize extensions at the module level ---
# These are "empty" shells until init_app is called with an app instance.
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
cache = Cache() # Create the global Cache instance. It will be configured by create_app.

def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # --- Logging Setup ---
    # ... (your logging setup as before) ...
    app.logger.info("LeadForge Backend Initializing...")


    # --- Initialize Flask Extensions ---
    # Order: db, migrate, login_manager, then cache
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app) 
    
    # --- Cache Initialization - Using the global 'cache' instance ---
    # Ensure CACHE_TYPE etc. are loaded from app.config (which comes from Config class)
    # If your Config class sets CACHE_TYPE, CACHE_DEFAULT_TIMEOUT, these setdefault calls
    # will only apply if those keys are missing from app.config.
    current_cache_config = {
        'CACHE_TYPE': app.config.get('CACHE_TYPE', 'SimpleCache'), # Get from app.config or default
        'CACHE_DEFAULT_TIMEOUT': app.config.get('CACHE_DEFAULT_TIMEOUT', 300)
        # Add other specific cache configs if needed, e.g., CACHE_REDIS_URL
    }
    print(f"DEBUG [create_app]: Cache config to be used: {current_cache_config}")
    
    # Initialize the *global* 'cache' object with the app and its specific config.
    # This ensures the 'cache' object imported by other modules (like utils.py via 'from . import cache')
    # is the one that's fully configured.
    cache.init_app(app, config=current_cache_config) 
    # --- END Cache Initialization ---

    # --- CRITICAL DEBUG PRINT FOR CACHE ---
    print(f"DEBUG [create_app]: ---- Verifying Cache in app.extensions ----")
    if 'cache' in app.extensions:
        cache_from_extensions = app.extensions['cache']
        print(f"DEBUG [create_app]: 'cache' key found in app.extensions.")
        print(f"DEBUG [create_app]: Type of app.extensions['cache']: {type(cache_from_extensions)}")
        if cache_from_extensions is cache: # Check if it's the SAME global object
            print("DEBUG [create_app]: app.extensions['cache'] IS the global cache object instance.")
        else:
            print("WARNING [create_app]: app.extensions['cache'] is NOT the global cache object instance. This is unexpected.")

        if hasattr(cache_from_extensions, 'get') and hasattr(cache_from_extensions, 'set'):
            print(f"SUCCESS [create_app]: app.extensions['cache'] (type: {type(cache_from_extensions)}) has get/set methods.")
        else:
            print(f"ALARM [create_app]: app.extensions['cache'] is a {type(cache_from_extensions)} but does NOT have get/set methods. Problem!")
    else:
        print("CRITICAL ERROR [create_app]: 'cache' key NOT FOUND in app.extensions after cache.init_app(app).")
    print(f"DEBUG [create_app]: ---- End Cache Verification ----")
    # --- END CRITICAL DEBUG PRINT ---

    # --- Flask-Login Configuration ---
    # ... (your login_manager setup as before) ...
    login_manager.login_view = 'auth_bp.login'
    from . import models 
    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    # --- CORS Configuration ---
    # ... (your CORS setup as before) ...
    frontend_url = app.config.get('FRONTEND_URL', 'http://localhost:5173')
    CORS(app, origins=[frontend_url, "http://localhost:5173"], supports_credentials=True, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-CSRFToken"])


    # --- Import and Register Blueprints ---
    # ... (your blueprint registrations as before) ...
    from .routes_auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    from .routes_leads import leads_bp
    app.register_blueprint(leads_bp, url_prefix='/api/leads')
    from .routes_search import search_bp
    app.register_blueprint(search_bp, url_prefix='/api/search')


    # --- Health Check Route ---
    # ... (your health check as before) ...
    
    app.logger.info("LeadForge Backend Initialized Successfully.")
    return app