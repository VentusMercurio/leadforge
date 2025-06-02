# leaddawg_pro_backend/app/routes_auth.py
from flask import Blueprint, request, jsonify, current_app
# werkzeug.security imports are not strictly needed here if User model handles hashing
# from werkzeug.security import generate_password_hash, check_password_hash 
from flask_login import login_user, logout_user, login_required, current_user

from . import db 
from .models import User 

auth_bp = Blueprint('auth_bp', __name__) # No url_prefix here; set during app.register_blueprint

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
        return jsonify(message="Username already exists"), 409
    
    if User.query.filter_by(email=email).first():
        return jsonify(message="Email already registered"), 409

    if len(password) < 8:
        return jsonify(message="Password must be at least 8 characters long"), 400

    new_user = User(username=username, email=email)
    new_user.set_password(password) # Assumes User model has this method
    
    try:
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user, remember=True) 
        current_app.logger.info(f"User {new_user.username} registered and logged in successfully.")
        return jsonify(
            message="User registered successfully", 
            user=new_user.to_dict() # Assumes User model has to_dict()
        ), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error during registration for {username}: {e}", exc_info=True)
        return jsonify(message="Registration failed due to an internal server error"), 500

@auth_bp.route('/login', methods=['GET', 'POST']) # <-- ADDED 'GET' METHOD HERE
def login():
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify(message="No input data provided"), 400

        login_identifier = data.get('email') # Frontend sends 'email' as the identifier
        password = data.get('password')

        if not login_identifier or not password:
            return jsonify(message="Email/username and password are required"), 400

        user = User.query.filter((User.username == login_identifier) | (User.email == login_identifier)).first()

        if user and user.check_password(password): # Assumes User model has check_password
            login_user(user, remember=data.get('remember', True)) 
            current_app.logger.info(f"User {user.username} logged in successfully.")
            return jsonify(
                message="Login successful", 
                user=current_user.to_dict() # Assumes User model has to_dict()
            ), 200
        else:
            current_app.logger.warning(f"Failed login attempt for identifier: {login_identifier}")
            return jsonify(message="Invalid credentials"), 401
    
    # Handle GET requests to /login
    # This is typically hit when Flask-Login redirects an unauthenticated user.
    # The frontend (LoginPage.jsx) is responsible for rendering the actual login form UI.
    # So, the API just needs to allow the GET request.
    # It doesn't need to return any specific data unless your frontend expects something.
    return jsonify(message="Login endpoint. Please POST credentials."), 200 # Or simply an empty 200 OK

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    current_app.logger.info(f"User {current_user.username} logging out.")
    logout_user()
    return jsonify(message="Logout successful"), 200

@auth_bp.route('/status', methods=['GET'])
@login_required
def status():
    return jsonify(
        isLoggedIn=True, 
        user=current_user.to_dict() # Assumes User model has to_dict()
    ), 200