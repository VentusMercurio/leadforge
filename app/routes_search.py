# leadforge_backend/app/routes_search.py
from flask import Blueprint, request, jsonify, current_app
from .utils import get_coordinates_for_city, fetch_osm_data, enrich_with_google_places
import time

search_bp = Blueprint('search_bp', __name__)

# YOUR EXISTING TAG_MAPPING (where values are single tuples)
TAG_MAPPING = {
    "bars": ("amenity", "bar"),
    "bar": ("amenity", "bar"), 
    "restaurants": ("amenity", "restaurant"),
    "restaurant": ("amenity", "restaurant"), 
    "cafes": ("amenity", "cafe"),
    "cafe": ("amenity", "cafe"), 
    "breweries": ("craft", "brewery"),
    "brewery": ("craft", "brewery"),
    "hotels": ("tourism", "hotel"),
    "hotel": ("tourism", "hotel"),
    "salons": ("shop", "hairdresser"),
    "salon": ("shop", "hairdresser"),
    "gyms": ("leisure", "fitness_centre"),
    "gym": ("leisure", "fitness_centre"),
    "supermarkets": ("shop", "supermarket"),
    "supermarket": ("shop", "supermarket"),
    "": ("amenity", "restaurant") 
}

# --- normalize_osm_result function (keep your existing one) ---
def normalize_osm_result(osm_element, google_enrichment=None):
    tags = osm_element.get("tags", {})
    name = (google_enrichment.get("name_google") if google_enrichment 
            else None) or tags.get("name", "Unknown Venue")
    osm_address_parts = [
        tags.get("addr:housenumber"), tags.get("addr:street"),
        tags.get("addr:city"), tags.get("addr:state"), tags.get("addr:postcode")
    ]
    osm_address = ", ".join(filter(None, osm_address_parts)) or None
    address = (google_enrichment.get("address_google") if google_enrichment 
               else None) or osm_address
    osm_categories = []
    if tags.get("amenity"): osm_categories.append(tags.get("amenity"))
    if tags.get("shop"): osm_categories.append(tags.get("shop"))
    if tags.get("leisure"): osm_categories.append(tags.get("leisure"))
    if tags.get("craft"): osm_categories.append(tags.get("craft"))
    final_types_array = osm_categories
    if google_enrichment and google_enrichment.get("types_google"):
        final_types_array = google_enrichment.get("types_google", [])
    lat = osm_element.get("lat")
    lon = osm_element.get("lon")
    if osm_element.get('type') != 'node' and 'center' in osm_element:
        lat = osm_element['center'].get('lat', lat)
        lon = osm_element['center'].get('lon', lon)
    return {
        "google_place_id": google_enrichment.get("google_place_id") if google_enrichment else None,
        "osm_id": f"{osm_element.get('type')}/{osm_element.get('id')}", "name": name, "address": address,
        "website": (google_enrichment.get("website_google") if google_enrichment else None) or tags.get("website") or tags.get("contact:website"),
        "phone_number": (google_enrichment.get("phone_number_google") if google_enrichment else None) or tags.get("phone") or tags.get("contact:phone"),
        "photo_url": google_enrichment.get("photo_url_google") if google_enrichment else None,
        "types": final_types_array, "rating": google_enrichment.get("rating_google") if google_enrichment else None,
        "user_ratings_total": google_enrichment.get("user_ratings_total_google") if google_enrichment else None,
        "business_status": google_enrichment.get("business_status_google") if google_enrichment else None,
        "opening_hours": google_enrichment.get("opening_hours_google") if google_enrichment else (tags.get("opening_hours")),
        "google_maps_url": google_enrichment.get("google_maps_url") if google_enrichment else None,
        "price_level": google_enrichment.get("price_level_google") if google_enrichment else None,
        "latitude": lat, "longitude": lon,
    }
# --- END normalize_osm_result ---


@search_bp.route('/osm-places', methods=['GET'])
def search_osm_places_route():
    query_term = request.args.get('query', '').strip().lower()
    location_name = request.args.get('location')
    enrich_google_str = request.args.get('enrich_google', 'false').lower()
    
    try:
        limit = int(request.args.get('limit', 30)) 
        if limit <= 0 or limit > 200: limit = 30 
    except ValueError:
        limit = 30

    current_app.logger.debug(f"API Call to /osm-places: query='{query_term}', location='{location_name}', enrich_google='{enrich_google_str}', limit={limit}")

    if not location_name:
        return jsonify(message="Missing 'location' parameter.", status="BAD_REQUEST"), 400

    # --- MODIFIED TAG HANDLING TO CREATE A LIST ---
    mapped_tag_tuple = TAG_MAPPING.get(query_term) # Gets a single tuple like ("amenity", "bar") or None

    osm_tag_conditions_list = [] # Initialize as empty list
    if mapped_tag_tuple:
        osm_tag_conditions_list = [mapped_tag_tuple] # Wrap the single tuple in a list
    elif query_term: # If a specific query was given but not in map
        current_app.logger.info(f"Query term '{query_term}' not in TAG_MAPPING. Defaulting to name search.")
        osm_tag_conditions_list = [("name", query_term)] # Search by name
    else: # Empty query term, and "" was not found or resulted in None (should be caught by TAG_MAPPING[""] if it exists)
        current_app.logger.warning(f"Empty query term and no default mapping found or mapping resulted in None.")
        return jsonify(message="Query term is required or a valid default mapping must exist.", status="BAD_REQUEST"), 400
    
    if not osm_tag_conditions_list: # Should not happen if logic above is correct, but as a safeguard
        current_app.logger.error(f"Failed to derive osm_tag_conditions_list for query '{query_term}'.")
        return jsonify(message="Could not determine search criteria.", status="INTERNAL_ERROR"), 500
    # --- END MODIFIED TAG HANDLING ---
            
    current_app.logger.info(f"Using OSM tag conditions for query '{query_term}': {osm_tag_conditions_list}")

    geo_data = get_coordinates_for_city(location_name)
    if not geo_data or 'bounding_box_str' not in geo_data:
        # ... (handle geocoding failure) ...
        current_app.logger.info(f"Could not geocode location: '{location_name}'")
        return jsonify(message=f"Could not geocode location: {location_name}", status="LOCATION_NOT_FOUND"), 200

    current_app.logger.info(f"Geocoded '{location_name}' to bbox: {geo_data['bounding_box_str']}")
    
    # --- CORRECTED CALL TO fetch_osm_data ---
    osm_elements = fetch_osm_data(
        tag_conditions_list=osm_tag_conditions_list, # Pass the list of conditions
        bounding_box_str=geo_data['bounding_box_str'], 
        limit=limit
    )
    # --- END CORRECTION ---
    
    if osm_elements is None: 
        current_app.logger.error(f"fetch_osm_data returned None for query '{query_term}'.")
        return jsonify(message="Error fetching data from OpenStreetMap/Overpass API.", status="OSM_API_ERROR"), 500
    
    current_app.logger.info(f"Found {len(osm_elements)} raw elements from OSM for query '{query_term}'.")

    # --- Filtering, Enrichment, Sorting (Your existing logic, ensure it uses filtered_osm_elements) ---
    # (Copied from your provided block, ensure variable names are consistent if you changed them)
    initial_count = len(osm_elements)
    def is_element_sufficiently_detailed(element):
        tags = element.get("tags", {})
        if not tags.get("name"): return False
        return True
    filtered_osm_elements = [el for el in osm_elements if is_element_sufficiently_detailed(el)]
    current_app.logger.info(f"Filtered from {initial_count} to {len(filtered_osm_elements)} elements after detail check.")

    if not filtered_osm_elements:
        return jsonify(status="ZERO_RESULTS", places=[], message=f"No sufficiently detailed OSM results for '{query_term}' in '{location_name}'."), 200

    processed_leads = []
    google_enrich_attempt_limit = 5 if enrich_google_str == 'true' else 0 
    enriched_count = 0
    processing_limit = len(filtered_osm_elements)

    for element in filtered_osm_elements[:processing_limit]:
        google_data_for_this_lead = None
        if enrich_google_str == 'true' and enriched_count < google_enrich_attempt_limit:
            osm_name = element.get("tags", {}).get("name")
            osm_lat = element.get("lat") or element.get("center", {}).get("lat")
            osm_lon = element.get("lon") or element.get("center", {}).get("lon")
            if osm_name and osm_lat and osm_lon:
                osm_address_tags = element.get("tags", {})
                addr_street = osm_address_tags.get("addr:street")
                addr_city_osm = osm_address_tags.get("addr:city")
                address_hint = addr_street
                if addr_city_osm: address_hint = f"{addr_street}, {addr_city_osm}" if addr_street else addr_city_osm
                elif geo_data.get('display_name'):
                    city_context_from_nominatim = geo_data['display_name'].split(',')[0].strip()
                    if address_hint: address_hint += f", {city_context_from_nominatim}"
                    else: address_hint = city_context_from_nominatim
                else: address_hint = location_name
                google_data_for_this_lead = enrich_with_google_places(osm_name, address=address_hint, latitude=osm_lat, longitude=osm_lon)
                if google_data_for_this_lead: enriched_count += 1
        
        normalized_lead = normalize_osm_result(element, google_data_for_this_lead)
        processed_leads.append(normalized_lead)

    def calculate_completeness_score(lead):
        score = 0
        if lead.get("name") and lead["name"] != "Unknown Venue": score += 5
        if lead.get("address"): score += 3
        if lead.get("phone_number"): score += 2
        if lead.get("website"): score += 2
        if lead.get("photo_url"): score += 1
        if lead.get("types") and len(lead.get("types")) > 0: score += 1
        if lead.get("rating"): score +=1
        return score
    if processed_leads:
        processed_leads.sort(key=lambda lead: calculate_completeness_score(lead), reverse=True)
    
    final_message = "OK"
    if not processed_leads:
        final_message = f"No displayable results for '{query_term}' in '{location_name}' after filtering/sorting."
        return jsonify(status="ZERO_RESULTS", places=[], message=final_message, count=0), 200
        
    current_app.logger.info(f"Returning {len(processed_leads)} processed leads. Enriched {enriched_count} with Google.")
    return jsonify(status="OK", places=processed_leads, count=len(processed_leads), message=final_message), 200