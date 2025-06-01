# leadforge_backend/app/models.py
from app import db, login_manager # Assuming db and login_manager are initialized in app/__init__.py
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, timezone # Use timezone aware UTC for consistency

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    __tablename__ = 'user' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True) # Allow null if using OAuth later, or always require
    
    # SaaS Tier and Stripe Information
    tier = db.Column(db.String(50), default='free', nullable=False)
    stripe_customer_id = db.Column(db.String(120), unique=True, index=True, nullable=True)
    stripe_subscription_id = db.Column(db.String(120), unique=True, index=True, nullable=True)
    subscription_active_until = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship: One User has many SavedLeads
    # 'owner' is how a SavedLead instance can refer back to its User (e.g., lead.owner)
    # 'lazy="dynamic"' means saved_leads will be a query object, not a list loaded immediately.
    saved_leads = db.relationship('SavedLead', backref='owner', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash: # Handle users who might not have a password (e.g. OAuth only)
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User id={self.id} username={self.username} email={self.email} tier={self.tier}>'

class SavedLead(db.Model):
    __tablename__ = 'saved_lead' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_savedlead_user_id'), nullable=False) # Added name for FK constraint
    
    # IDs from different sources - making them all nullable as a lead might not exist on all platforms
    google_place_id = db.Column(db.String(255), index=True, nullable=True)
    osm_id = db.Column(db.String(255), index=True, nullable=True) 
    yelp_id = db.Column(db.String(255), index=True, nullable=True)

    # Core Info (try to normalize from various sources)
    name = db.Column(db.String(255), nullable=False) # Name should always be present
    address = db.Column(db.String(500), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    website = db.Column(db.String(500), nullable=True)
    categories_text = db.Column(db.Text, nullable=True) # Store as comma-separated string or JSON string

    # Source-specific rich data (can be JSON strings or separate tables for more structure)
    google_photo_url = db.Column(db.String(1024), nullable=True)
    google_rating = db.Column(db.Float, nullable=True)
    google_user_ratings_total = db.Column(db.Integer, nullable=True)
    google_maps_url = db.Column(db.String(1024), nullable=True)
    google_opening_hours = db.Column(db.Text, nullable=True) # Store as JSON string or similar
    google_business_status = db.Column(db.String(50), nullable=True)
    
    yelp_photo_url = db.Column(db.String(1024), nullable=True)
    yelp_rating = db.Column(db.Float, nullable=True)
    yelp_review_count = db.Column(db.Integer, nullable=True)
    yelp_price_range = db.Column(db.String(10), nullable=True)
    # yelp_categories = db.Column(db.Text, nullable=True) # Could store as JSON string

    # User-managed data
    user_status = db.Column(db.String(50), default='New', nullable=False)
    user_notes = db.Column(db.Text, nullable=True)
    
    saved_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        # Helper to convert essential fields to a dictionary for JSON responses
        # This is what your frontend (e.g., DashboardPage, LeadDetailView) will primarily consume
        return {
            'id': self.id,
            'user_id': self.user_id,
            'google_place_id': self.google_place_id,
            'osm_id': self.osm_id,
            'yelp_id': self.yelp_id,
            'name': self.name, # Use the primary 'name' field
            'address': self.address, # Use the primary 'address' field
            'phone': self.phone, # Use the primary 'phone' field
            'website': self.website, # Use the primary 'website' field
            'categories': self.categories_text.split(',') if self.categories_text else [],
            'photo_url': self.google_photo_url or self.yelp_photo_url, # Prioritize one, or offer both
            'rating': self.google_rating if self.google_rating is not None else self.yelp_rating, # Prioritize
            'user_ratings_total': self.google_user_ratings_total if self.google_user_ratings_total is not None else self.yelp_review_count,
            'business_status': self.google_business_status, # Primarily from Google
            'opening_hours_text': self.google_opening_hours, # Assuming Google's for now
            'google_maps_url': self.google_maps_url,
            'user_status': self.user_status,
            'user_notes': self.user_notes,
            'saved_at': self.saved_at.isoformat() + 'Z' if self.saved_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
        }

    def __repr__(self):
        return f'<SavedLead id={self.id} name="{self.name}" user_id={self.user_id}>'