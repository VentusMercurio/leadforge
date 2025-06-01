# config.py
import os
from dotenv import load_dotenv
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'another-super-secret-key-for-leadforge'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'leadforge.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FLASK_DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'

    GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY')
    FRONTEND_URL = os.environ.get('FRONTEND_URL')
    
    OVERPASS_API_URL = os.environ.get('OVERPASS_API_URL', 'https://overpass-api.de/api/interpreter')
    NOMINATIM_API_URL = os.environ.get('NOMINATIM_API_URL', 'https://nominatim.openstreetmap.org/search')