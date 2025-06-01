# leaddawg_pro_backend/app/routes_auth.py
from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import User # Assuming your User model is in app/models.py

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify(message="No input data provided"), 400

    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify(message="Username, email, and password are required"), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify(message="Username already exists"), 409 # Conflict
    
    if User.query.filter_by(email=email).first():
        return jsonify(message="Email already registered"), 409

    if len(password) < 8: # Basic password length validation
        return jsonify(message="Password must be at least 8 characters long"), 400

    new_user = User(username=username, email=email)
    new_user.set_password(password) # Hashes the password via the method in User model
    
    try:
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user, remember=True) # Log in user immediately, consider 'remember'
        current_app.logger.info(f"User {new_user.username} registered and logged in successfully.")
        return jsonify(
            message="User registered successfully", 
            user={
                'id': new_user.id, 
                'username': new_user.username,
                'email': new_user.email,
                'tier': new_user.tier # User model has default 'free'
            }
        ), 201 # 201 Created
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error during registration for {username}: {e}", exc_info=True)
        return jsonify(message="Registration failed due to an internal server error"), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify(message="No input data provided"), 400

    identifier = data.get('identifier') # Can be username or email
    password = data.get('password')

    if not identifier or not password:
        return jsonify(message="Username/email and password are required"), 400

    user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()

    if user and user.check_password(password):
        login_user(user, remember=data.get('remember', False)) # 'remember' can be a checkbox on frontend
        current_app.logger.info(f"User {user.username} logged in successfully.")
        return jsonify(
            message="Login successful", 
            user={
                'id': current_user.id, 
                'username': current_user.username,
                'email': current_user.email,
                'tier': current_user.tier
            }
        ), 200
    else:
        current_app.logger.warning(f"Failed login attempt for identifier: {identifier}")
        return jsonify(message="Invalid username/email or password"), 401 # 401 Unauthorized

@auth_bp.route('/logout', methods=['POST'])
@login_required # Ensures only logged-in users can logout
def logout():
    if current_user.is_authenticated:
        current_app.logger.info(f"User {current_user.username} logging out.")
        logout_user()
        return jsonify(message="Logout successful"), 200
    else: # Should not happen if @login_required is effective
        return jsonify(message="No user currently logged in."), 400


@auth_bp.route('/status', methods=['GET'])
@login_required # Ensures only logged-in users can check their status
def status():
    # current_user is provided by Flask-Login
    return jsonify(
        logged_in=True, 
        user={
            'id': current_user.id, 
            'username': current_user.username, 
            'email': current_user.email,
            'tier': current_user.tier
        }
    ), 200