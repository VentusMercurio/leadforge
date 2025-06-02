# leadforge_backend/app/routes_leads.py
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from . import db # Assuming db is initialized in app/__init__.py and imported correctly
from .models import SavedLead, User # Ensure User is imported if type hints or direct use occur
from .utils import enrich_with_google_places # <--- IMPORT YOUR UTILITY FUNCTION

# Ensure blueprint name matches what's used in app/__init__.py for registration
# If app/__init__.py has app.register_blueprint(leads_bp, url_prefix='/api/leads')
# then this Blueprint should not have a url_prefix.
leads_bp = Blueprint('leads_bp', __name__)

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
    if not google_place_id and not osm_id: # Require at least one of these for identification
        return jsonify(message="An external ID (Google Place ID or OSM ID) is required"), 400

    # Check if lead already saved by this user
    query_filter = (SavedLead.user_id == current_user.id)
    # Prioritize checking by google_place_id if available, then osm_id
    if google_place_id:
        existing_saved_lead = SavedLead.query.filter(query_filter & (SavedLead.google_place_id == google_place_id)).first()
    elif osm_id: # Only check by osm_id if google_place_id was not provided in payload or not found by it
        existing_saved_lead = SavedLead.query.filter(query_filter & (SavedLead.osm_id == osm_id)).first()
    else: # Should not happen due to check above, but as a fallback
        existing_saved_lead = None 
    
    if existing_saved_lead:
        current_app.logger.info(f"Lead '{name}' already saved by user {current_user.id} (Google ID: {google_place_id}, OSM ID: {osm_id})")
        return jsonify(message="Lead already saved by this user", lead=existing_saved_lead.to_dict()), 409 # Conflict

    categories_payload = data.get('types') # Frontend sends 'types' as an array
    categories_text_to_save = None
    if isinstance(categories_payload, list):
        categories_text_to_save = ",".join(categories_payload)
    elif isinstance(categories_payload, str):
        categories_text_to_save = categories_payload
    elif data.get('categories_text'): 
        categories_text_to_save = data.get('categories_text')

    opening_hours_payload = data.get('opening_hours')
    opening_hours_to_save = None
    if isinstance(opening_hours_payload, list):
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
        phone=data.get('phone_number'), # Frontend payload has 'phone_number'
        website=data.get('website'),
        categories_text=categories_text_to_save,
        
        google_photo_url=data.get('photo_url'), 
        google_rating=data.get('rating'),       
        google_user_ratings_total=data.get('user_ratings_total'), 
        google_maps_url=data.get('google_maps_url'),
        google_opening_hours=opening_hours_to_save, 
        google_business_status=data.get('business_status'),
        # If you add price_level to SavedLead model:
        # price_level=data.get('price_level'), 

        user_status=data.get('user_status', 'New') # Default to 'New' if not provided
    )

    try:
        db.session.add(new_lead)
        db.session.commit()
        current_app.logger.info(f"Lead '{new_lead.name}' (ID: {new_lead.id}) saved for user {current_user.id}. Address: {new_lead.address}")
        return jsonify(message="Lead saved successfully", lead=new_lead.to_dict()), 201 # 201 Created
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving lead for user {current_user.id}: {e}", exc_info=True)
        return jsonify(message="Failed to save lead due to an internal server error"), 500

@leads_bp.route('', methods=['GET']) 
@login_required
def get_saved_leads():
    # TODO: Implement pagination for GET all leads if many leads are expected per user
    user_leads = SavedLead.query.filter_by(user_id=current_user.id).order_by(SavedLead.saved_at.desc()).all()
    leads_list = [lead.to_dict() for lead in user_leads]
    current_app.logger.debug(f"Returning {len(leads_list)} saved leads for user {current_user.id}")
    return jsonify(leads=leads_list), 200
 
@leads_bp.route('/<int:lead_id>', methods=['PUT'])
@login_required
def update_saved_lead(lead_id):
    # first_or_404 automatically raises 404 if not found
    lead_to_update = SavedLead.query.filter_by(id=lead_id, user_id=current_user.id).first_or_404(
        description=f"Saved lead with id {lead_id} not found or not owned by user."
    )
    
    data = request.get_json()
    if not data:
        return jsonify(message="No update data provided"), 400

    updated_fields = []
    # Define valid statuses, perhaps from a config or constants file later
    VALID_STATUSES = ["New", "Contacted", "Followed Up", "Interested", "Booked", "Not Interested", "Pending"] 

    if 'user_status' in data:
        if data['user_status'] not in VALID_STATUSES: # Validate status
            return jsonify(message=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"), 400
        if lead_to_update.user_status != data['user_status']:
            lead_to_update.user_status = data['user_status']
            updated_fields.append('user_status')
    
    # For notes, allow setting to empty string or null (which DB might convert to None)
    if 'user_notes' in data: 
        if lead_to_update.user_notes != data['user_notes']: # Check if actually changed
            lead_to_update.user_notes = data['user_notes']
            updated_fields.append('user_notes')
    
    # Potentially allow updating other core fields if design requires
    # if 'name' in data and lead_to_update.name != data['name']: lead_to_update.name = data['name']; updated_fields.append('name')
    # ... etc. for phone, website, address

    if not updated_fields:
        # If no fields were actually changed, you could return a 304 Not Modified,
        # but for simplicity, a 200 OK with a message is also fine.
        return jsonify(message="No changes detected or no valid fields provided for update.", lead=lead_to_update.to_dict()), 200

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
    lead_to_delete = SavedLead.query.filter_by(id=lead_id, user_id=current_user.id).first_or_404(
         description=f"Saved lead with id {lead_id} not found or not owned by user."
    )

    try:
        db.session.delete(lead_to_delete)
        db.session.commit()
        current_app.logger.info(f"Lead ID {lead_id} deleted by user {current_user.id}.")
        return jsonify(message="Lead deleted successfully"), 200 # 204 No Content is also an option
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting lead {lead_id}: {e}", exc_info=True)
        return jsonify(message="Failed to delete lead due to an internal server error"), 500

# --- NEW ENDPOINT FOR TARGETED ENRICHMENT ---
@leads_bp.route('/<int:lead_id>/enrich', methods=['PUT']) # Using PUT as it idempotent-ly updates resource state
@login_required
def enrich_saved_lead_route(lead_id):
    saved_lead = SavedLead.query.filter_by(id=lead_id, user_id=current_user.id).first_or_404(
        description=f"Saved lead with id {lead_id} not found for this user."
    )

    current_app.logger.info(f"Attempting to enrich SavedLead ID: {saved_lead.id}, Name: '{saved_lead.name}' for user {current_user.id}")

    # Optional: Add a flag to your SavedLead model like `is_google_enriched` (Boolean)
    # and/or `last_google_enriched_at` (DateTime) to manage re-enrichment.
    # force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
    # if saved_lead.is_google_enriched and not force_refresh:
    #     current_app.logger.info(f"Lead {saved_lead.id} already Google enriched. Skipping unless forced.")
    #     return jsonify(message="Lead already enriched.", lead=saved_lead.to_dict()), 200

    google_data = None
    if not saved_lead.name: # Name is essential for a good quality Google Places search
        current_app.logger.warning(f"Cannot enrich lead {saved_lead.id} due to missing name.")
        return jsonify(message="Lead name is required for Google Places enrichment."), 400
        
    current_app.logger.debug(f"Calling enrich_with_google_places for: '{saved_lead.name}', Address: '{saved_lead.address}', Lat: {saved_lead.latitude}, Lon: {saved_lead.longitude}")
    google_data = enrich_with_google_places( # This utility should handle caching internally
        business_name=saved_lead.name, 
        address=saved_lead.address, 
        latitude=saved_lead.latitude, 
        longitude=saved_lead.longitude
    )

    if google_data:
        current_app.logger.info(f"Google enrichment successful for lead {saved_lead.id}.")
        any_field_updated = False

        # Update fields only if new data is available and different (or if you want to always overwrite)
        if google_data.get('google_place_id') and saved_lead.google_place_id != google_data.get('google_place_id'):
            saved_lead.google_place_id = google_data.get('google_place_id'); any_field_updated = True
        if google_data.get('name_google') and saved_lead.name != google_data.get('name_google'): # Prefer Google's name
            saved_lead.name = google_data.get('name_google'); any_field_updated = True
        if google_data.get('address_google') and saved_lead.address != google_data.get('address_google'): # Prefer Google's address
            saved_lead.address = google_data.get('address_google'); any_field_updated = True
        if google_data.get('phone_number_google') and saved_lead.phone != google_data.get('phone_number_google'):
            saved_lead.phone = google_data.get('phone_number_google'); any_field_updated = True
        if google_data.get('website_google') and saved_lead.website != google_data.get('website_google'):
            saved_lead.website = google_data.get('website_google'); any_field_updated = True
        
        if google_data.get('photo_url_google') and saved_lead.google_photo_url != google_data.get('photo_url_google'):
            saved_lead.google_photo_url = google_data.get('photo_url_google'); any_field_updated = True
        if google_data.get('rating_google') is not None and saved_lead.google_rating != google_data.get('rating_google'): # Check for None as 0 is valid
            saved_lead.google_rating = google_data.get('rating_google'); any_field_updated = True
        if google_data.get('user_ratings_total_google') is not None and saved_lead.google_user_ratings_total != google_data.get('user_ratings_total_google'):
            saved_lead.google_user_ratings_total = google_data.get('user_ratings_total_google'); any_field_updated = True
        if google_data.get('google_maps_url') and saved_lead.google_maps_url != google_data.get('google_maps_url'):
            saved_lead.google_maps_url = google_data.get('google_maps_url'); any_field_updated = True
        if google_data.get('business_status_google') and saved_lead.google_business_status != google_data.get('business_status_google'):
            saved_lead.google_business_status = google_data.get('business_status_google'); any_field_updated = True
        
        opening_hours_payload = google_data.get('opening_hours_google')
        new_opening_hours_text = None
        if isinstance(opening_hours_payload, list):
            new_opening_hours_text = "\n".join(opening_hours_payload)
        elif isinstance(opening_hours_payload, str):
            new_opening_hours_text = opening_hours_payload
        if new_opening_hours_text is not None and saved_lead.google_opening_hours != new_opening_hours_text:
            saved_lead.google_opening_hours = new_opening_hours_text; any_field_updated = True

        google_types = google_data.get('types_google')
        if isinstance(google_types, list) and google_types:
            new_categories_text = ",".join(google_types)
            if saved_lead.categories_text != new_categories_text:
                saved_lead.categories_text = new_categories_text; any_field_updated = True
        
        if any_field_updated:
            try:
                # saved_lead.is_google_enriched = True # If you add this flag
                # saved_lead.last_google_enriched_at = datetime.now(timezone.utc) # Update timestamp
                db.session.commit()
                current_app.logger.info(f"Lead {saved_lead.id} successfully enriched and updated in DB.")
                return jsonify(message="Lead enriched and updated successfully", lead=saved_lead.to_dict()), 200
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error saving enriched lead {saved_lead.id}: {e}", exc_info=True)
                return jsonify(message="Failed to save enriched lead data due to server error"), 500
        else:
            current_app.logger.info(f"Enrichment for lead {saved_lead.id} resulted in no new data changes.")
            return jsonify(message="Enrichment complete, no new data to update.", lead=saved_lead.to_dict()), 200 # Or 304 Not Modified
    else:
        current_app.logger.info(f"No Google enrichment data could be found for lead {saved_lead.id}.")
        return jsonify(message="No enrichment data found from Google for this lead.", lead=saved_lead.to_dict()), 200 # Or 404 if you prefer
# --- END NEW ENDPOINT ---