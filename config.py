# config.py
import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env')) # Load .env file from the same directory as config.py

class Config:
    # --- Core Flask Settings ---
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'fallback-super-secret-key-leadforge' # Essential for sessions
    FLASK_DEBUG = os.environ.get('FLASK_DEBUG', '0').lower() in ['true', '1', 't'] # More robust boolean check

    # --- Database Settings ---
    # Your DATABASE_URL in .env should be 'sqlite:///leadforge.db' for instance folder usage
    # The fallback here constructs an absolute path to project_root/instance/leadforge.db
    # This might differ slightly from how app.instance_path works if 'basedir' isn't project root.
    # For consistency with app.instance_path, ensure DATABASE_URL in .env is just 'sqlite:///leadforge.db'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.dirname(basedir), 'instance', 'leadforge.db') # Assuming 'instance' is sibling to 'app'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- External API Keys & URLs ---
    GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY')
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5173') # Good to have a default
    
    OVERPASS_API_URL = os.environ.get('OVERPASS_API_URL', 'https://overpass-api.de/api/interpreter')
    NOMINATIM_API_URL = os.environ.get('NOMINATIM_API_URL', 'https://nominatim.openstreetmap.org/search')

    # --- Flask-Login Session Cookie Settings ---
    # These are important for development, especially with cross-origin (different port) frontend
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ['true', '1', 't'] # False for HTTP
    SESSION_COOKIE_HTTPONLY = True  # Default, good for security
    SESSION_COOKIE_SAMESITE = 'Lax' # Default, generally okay for localhost. 'None' requires Secure=True.
    # If using "Remember Me" functionality with Flask-Login:
    # REMEMBER_COOKIE_DURATION = timedelta(days=30) # Example
    # REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE # Match session cookie
    # REMEMBER_COOKIE_HTTPONLY = True
    # REMEMBER_COOKIE_SAMESITE = 'Lax'

    # --- Stripe Keys (if/when you add them back) ---
    # STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    # STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    # STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')