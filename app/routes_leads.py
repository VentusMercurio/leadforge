# leadforge_backend/app/routes_leads.py
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import SavedLead, User # Make sure User is imported if needed for type hinting or context

leads_bp = Blueprint('leads', __name__, url_prefix='/api/leads')

@leads_bp.route('', methods=['POST'])
@login_required
def save_new_lead():
    data = request.get_json()
    if not data:
        return jsonify(message="No input data provided"), 400

    # Essential identifier, e.g., from Google or OSM search result
    # The frontend should decide which ID is primary if multiple exist (e.g. prefer google_place_id)
    google_place_id = data.get('google_place_id') 
    osm_id = data.get('osm_id')
    name = data.get('name')

    if not name: # Name is essential
        return jsonify(message="Lead name is required"), 400
    if not google_place_id and not osm_id: # At least one external ID should be present
        return jsonify(message="An external ID (Google Place ID or OSM ID) is required"), 400

    # Check if this user has already saved this lead based on available IDs
    # Prioritize Google Place ID if available
    query_filter = (SavedLead.user_id == current_user.id)
    if google_place_id:
        query_filter &= (SavedLead.google_place_id == google_place_id)
    elif osm_id: # Fallback to OSM ID if Google ID not provided
        query_filter &= (SavedLead.osm_id == osm_id)
    
    existing_saved_lead = SavedLead.query.filter(query_filter).first()
    
    if existing_saved_lead:
        # Optionally update if new data is better, or just return conflict
        # For now, let's just return conflict if a primary ID matches.
        current_app.logger.info(f"Lead '{name}' already saved by user {current_user.id} (Google ID: {google_place_id}, OSM ID: {osm_id})")
        return jsonify(message="Lead already saved by this user", lead=existing_saved_lead.to_dict()), 409

    # Create new SavedLead with all available data from the frontend
    new_lead = SavedLead(
        user_id=current_user.id,
        name=name,
        google_place_id=google_place_id,
        osm_id=osm_id,
        yelp_id=data.get('yelp_id'), # For future Yelp integration
        address=data.get('address'),
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        phone=data.get('phone_number') or data.get('phone'), # Accept 'phone_number' or 'phone'
        website=data.get('website'),
        categories_text=",".join(data.get('types', [])) if data.get('types') else data.get('categories'), # Handle 'types' or 'categories'
        
        google_photo_url=data.get('photo_url') or data.get('google_photo_url'), # Accept 'photo_url' or 'google_photo_url'
        google_rating=data.get('rating') if data.get('google_place_id') else data.get('google_rating'),
        google_user_ratings_total=data.get('user_ratings_total') if data.get('google_place_id') else data.get('google_user_ratings_total'),
        google_maps_url=data.get('google_maps_url'),
        google_opening_hours=data.get('opening_hours_text') or data.get('opening_hours'), # Store as text/JSON
        google_business_status=data.get('business_status'),

        user_status=data.get('user_status', 'New')
        # user_notes will be empty initially, updated via PUT
    )

    try:
        db.session.add(new_lead)
        db.session.commit()
        current_app.logger.info(f"Lead '{new_lead.name}' saved for user {current_user.id}")
        return jsonify(message="Lead saved successfully", lead=new_lead.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving lead for user {current_user.id}: {e}", exc_info=True)
        return jsonify(message="Failed to save lead due to an internal server error"), 500

@leads_bp.route('', methods=['GET'])
@login_required
def get_saved_leads():
    user_leads = SavedLead.query.filter_by(user_id=current_user.id).order_by(SavedLead.saved_at.desc()).all()
    leads_list = [lead.to_dict() for lead in user_leads]
    return jsonify(leads=leads_list), 200

@leads_bp.route('/<int:lead_id>', methods=['PUT'])
@login_required
def update_saved_lead(lead_id):
    lead_to_update = SavedLead.query.get_or_404(lead_id)
    if lead_to_update.owner != current_user:
        return jsonify(message="Unauthorized to update this lead"), 403

    data = request.get_json()
    if not data:
        return jsonify(message="No update data provided"), 400

    updated_fields = []
    if 'user_status' in data:
        # VALID_STATUSES can be defined globally or imported
        VALID_STATUSES = ["New", "Contacted", "Followed Up", "Interested", "Booked", "Not Interested", "Pending"]
        if data['user_status'] not in VALID_STATUSES:
            return jsonify(message=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"), 400
        lead_to_update.user_status = data['user_status']
        updated_fields.append('status')
    
    if 'user_notes' in data: # Allows sending null to clear notes
        lead_to_update.user_notes = data['user_notes']
        updated_fields.append('notes')
    
    # Add other updatable fields here if needed, e.g., manually overriding phone/website
    # if 'phone' in data: lead_to_update.phone = data['phone']
    # if 'website' in data: lead_to_update.website = data['website']

    if not updated_fields:
        return jsonify(message="No valid fields provided for update"), 400

    try:
        db.session.commit()
        current_app.logger.info(f"Lead ID {lead_id} updated by user {current_user.id}. Fields: {', '.join(updated_fields)}")
        return jsonify(message="Lead updated successfully", lead=lead_to_update.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating lead {lead_id}: {e}", exc_info=True)
        return jsonify(message="Failed to update lead due to an internal server error"), 500

@leads_bp.route('/<int:lead_id>', methods=['DELETE'])
@login_required
def delete_saved_lead(lead_id):
    lead_to_delete = SavedLead.query.get_or_404(lead_id)
    if lead_to_delete.owner != current_user:
        return jsonify(message="Unauthorized to delete this lead"), 403
    try:
        db.session.delete(lead_to_delete)
        db.session.commit()
        current_app.logger.info(f"Lead ID {lead_id} deleted by user {current_user.id}.")
        return jsonify(message="Lead deleted successfully"), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting lead {lead_id}: {e}", exc_info=True)
        return jsonify(message="Failed to delete lead due to an internal server error"), 500