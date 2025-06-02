# leadforge_backend/app/routes_leads.py
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from . import db # Assuming db is initialized in app/__init__.py and imported correctly
from .models import SavedLead, User # Ensure User is imported if type hints or direct use occur

# Ensure blueprint name matches what's used in app/__init__.py for registration
leads_bp = Blueprint('leads_bp', __name__) # Using a consistent naming like leads_bp or leads_module_bp

@leads_bp.route('', methods=['POST']) # Corresponds to /api/leads (if prefix is /api/leads in __init__)
@login_required
def save_new_lead():
    data = request.get_json()
    current_app.logger.debug(f"Received payload for new lead: {data}")

    if not data:
        return jsonify(message="No input data provided"), 400

    name = data.get('name')
    google_place_id = data.get('google_place_id') 
    osm_id = data.get('osm_id')

    if not name:
        return jsonify(message="Lead name is required"), 400
    if not google_place_id and not osm_id:
        return jsonify(message="An external ID (Google Place ID or OSM ID) is required"), 400

    query_filter = (SavedLead.user_id == current_user.id)
    if google_place_id:
        query_filter &= (SavedLead.google_place_id == google_place_id)
    elif osm_id: 
        query_filter &= (SavedLead.osm_id == osm_id)
    
    existing_saved_lead = SavedLead.query.filter(query_filter).first()
    
    if existing_saved_lead:
        current_app.logger.info(f"Lead '{name}' already saved by user {current_user.id} (Google ID: {google_place_id}, OSM ID: {osm_id})")
        return jsonify(message="Lead already saved by this user", lead=existing_saved_lead.to_dict()), 409

    # --- Refined new_lead creation based on discussion ---
    categories_payload = data.get('types') # Frontend sends 'types' as an array
    categories_text_to_save = None
    if isinstance(categories_payload, list):
        categories_text_to_save = ",".join(categories_payload)
    elif isinstance(categories_payload, str): # Fallback if it's already a string (e.g. from other source)
        categories_text_to_save = categories_payload
    # Add another fallback to 'categories_text' if frontend might send that directly
    elif data.get('categories_text'): 
        categories_text_to_save = data.get('categories_text')

    opening_hours_payload = data.get('opening_hours') # Frontend sends 'opening_hours'
    opening_hours_to_save = None
    if isinstance(opening_hours_payload, list): # Google often provides this as an array of strings
        opening_hours_to_save = "\n".join(opening_hours_payload)
    elif isinstance(opening_hours_payload, str):
        opening_hours_to_save = opening_hours_payload
    
    new_lead = SavedLead(
        user_id=current_user.id,
        name=name,
        google_place_id=google_place_id,
        osm_id=osm_id,
        yelp_id=data.get('yelp_id'), 
        
        address=data.get('address'),
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        phone=data.get('phone_number'), # Frontend sends 'phone_number' in payload
        website=data.get('website'),
        categories_text=categories_text_to_save,
        
        google_photo_url=data.get('photo_url'), # Frontend sends 'photo_url' (which is google_photo_url)
        google_rating=data.get('rating'),       # Frontend sends 'rating' (which is google_rating)
        google_user_ratings_total=data.get('user_ratings_total'), # Frontend sends 'user_ratings_total'
        google_maps_url=data.get('google_maps_url'),
        google_opening_hours=opening_hours_to_save, 
        google_business_status=data.get('business_status'),
        # price_level=data.get('price_level'), # If you add price_level to SavedLead model

        user_status=data.get('user_status', 'New')
    )
    # --- End of refined new_lead creation ---

    try:
        db.session.add(new_lead)
        db.session.commit()
        current_app.logger.info(f"Lead '{new_lead.name}' (ID: {new_lead.id}) saved for user {current_user.id}. Address: {new_lead.address}")
        return jsonify(message="Lead saved successfully", lead=new_lead.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving lead for user {current_user.id}: {e}", exc_info=True)
        return jsonify(message="Failed to save lead due to an internal server error"), 500

@leads_bp.route('', methods=['GET']) # Corresponds to /api/leads
@login_required
def get_saved_leads():
    # Consider adding pagination here if a user can have many saved leads
    # page = request.args.get('page', 1, type=int)
    # per_page = request.args.get('per_page', 20, type=int)
    # user_leads_paginated = SavedLead.query.filter_by(user_id=current_user.id).order_by(SavedLead.saved_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    # leads_list = [lead.to_dict() for lead in user_leads_paginated.items]
    # return jsonify(
    #     leads=leads_list,
    #     total=user_leads_paginated.total,
    #     pages=user_leads_paginated.pages,
    #     current_page=user_leads_paginated.page
    # ), 200
    
    user_leads = SavedLead.query.filter_by(user_id=current_user.id).order_by(SavedLead.saved_at.desc()).all()
    leads_list = [lead.to_dict() for lead in user_leads]
    current_app.logger.debug(f"Returning {len(leads_list)} saved leads for user {current_user.id}")
    return jsonify(leads=leads_list), 200
 
@leads_bp.route('/<int:lead_id>', methods=['PUT']) # Corresponds to /api/leads/<lead_id>
@login_required
def update_saved_lead(lead_id):
    lead_to_update = SavedLead.query.filter_by(id=lead_id, user_id=current_user.id).first_or_404(
        description=f"Saved lead with id {lead_id} not found for this user."
    )
    # No need for: if lead_to_update.owner != current_user, as the query above handles it.

    data = request.get_json()
    if not data:
        return jsonify(message="No update data provided"), 400

    updated_fields = []
    VALID_STATUSES = ["New", "Contacted", "Followed Up", "Interested", "Booked", "Not Interested", "Pending"] # Define centrally if used elsewhere

    if 'user_status' in data:
        if data['user_status'] not in VALID_STATUSES:
            return jsonify(message=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"), 400
        lead_to_update.user_status = data['user_status']
        updated_fields.append('user_status')
    
    if 'user_notes' in data: # Allows sending null or empty string to clear notes
        lead_to_update.user_notes = data['user_notes']
        updated_fields.append('user_notes')
    
    # Add other updatable fields here by user if needed from frontend form
    # Example: if frontend allows editing basic lead info that might have changed from OSM/Google
    # if 'name' in data: lead_to_update.name = data['name']; updated_fields.append('name')
    # if 'phone' in data: lead_to_update.phone = data['phone']; updated_fields.append('phone')
    # if 'website' in data: lead_to_update.website = data['website']; updated_fields.append('website')
    # if 'address' in data: lead_to_update.address = data['address']; updated_fields.append('address')


    if not updated_fields:
        return jsonify(message="No valid fields provided for update or no changes detected"), 400 # Or 304 Not Modified if no actual changes

    try:
        db.session.commit()
        current_app.logger.info(f"Lead ID {lead_id} updated by user {current_user.id}. Fields: {', '.join(updated_fields)}")
        return jsonify(message="Lead updated successfully", lead=lead_to_update.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating lead {lead_id}: {e}", exc_info=True)
        return jsonify(message="Failed to update lead due to an internal server error"), 500

@leads_bp.route('/<int:lead_id>', methods=['DELETE']) # Corresponds to /api/leads/<lead_id>
@login_required
def delete_saved_lead(lead_id):
    lead_to_delete = SavedLead.query.filter_by(id=lead_id, user_id=current_user.id).first_or_404(
         description=f"Saved lead with id {lead_id} not found for this user."
    )
    # No need for: if lead_to_delete.owner != current_user

    try:
        db.session.delete(lead_to_delete)
        db.session.commit()
        current_app.logger.info(f"Lead ID {lead_id} deleted by user {current_user.id}.")
        return jsonify(message="Lead deleted successfully"), 200 # Or 204 No Content
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting lead {lead_id}: {e}", exc_info=True)
        return jsonify(message="Failed to delete lead due to an internal server error"), 500