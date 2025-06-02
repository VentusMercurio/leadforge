# leadforge_backend/app/routes_search.py
from flask import Blueprint, request, jsonify, current_app
# Ensure correct relative import for utils based on your project structure
# If routes_search.py and utils.py are siblings in 'app/', then '.utils' is correct.
from .utils import get_coordinates_for_city, fetch_osm_data, enrich_with_google_places
import time

# This is the Blueprint instance that app/__init__.py will import
search_bp = Blueprint('search_bp', __name__)

# OSM Tag Mapping: user query_term -> (osm_key, osm_value)
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
    # Default for empty query or unmapped terms (optional, can be handled differently)
    "": ("amenity", "restaurant") # Example: default to restaurants if query is empty
}

def normalize_osm_result(osm_element, google_enrichment=None):
    """
    Converts an OSM element and optional Google data into the app's standard lead format
    for search results.
    """
    tags = osm_element.get("tags", {})
    
    # Prioritize Google data if enrichment happened, otherwise use OSM data
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
    
    final_types_array = osm_categories # Start with OSM categories
    if google_enrichment and google_enrichment.get("types_google"):
        # Option: Prioritize Google types, or merge and deduplicate
        final_types_array = google_enrichment.get("types_google", []) 
        # Example merge: final_types_array = list(set(osm_categories + google_enrichment.get("types_google", [])))


    lat = osm_element.get("lat")
    lon = osm_element.get("lon")
    if osm_element.get('type') != 'node' and 'center' in osm_element: # For ways/relations
        lat = osm_element['center'].get('lat', lat)
        lon = osm_element['center'].get('lon', lon)

    # This structure should align with what ResultsPage.jsx expects for 'placeToSave'
    # and what its LeadCard displays.
    return {
        "google_place_id": google_enrichment.get("google_place_id") if google_enrichment else None,
        "osm_id": f"{osm_element.get('type')}/{osm_element.get('id')}",
        "name": name,
        "address": address,
        "website": (google_enrichment.get("website_google") if google_enrichment else None) or tags.get("website") or tags.get("contact:website"),
        "phone_number": (google_enrichment.get("phone_number_google") if google_enrichment else None) or tags.get("phone") or tags.get("contact:phone"),
        "photo_url": google_enrichment.get("photo_url_google") if google_enrichment else None, # Primarily Google photo
        "types": final_types_array, # Send as array
        "rating": google_enrichment.get("rating_google") if google_enrichment else None,
        "user_ratings_total": google_enrichment.get("user_ratings_total_google") if google_enrichment else None,
        "business_status": google_enrichment.get("business_status_google") if google_enrichment else None,
        "opening_hours": google_enrichment.get("opening_hours_google") if google_enrichment else (tags.get("opening_hours")), # Raw OSM opening_hours string or Google array
        "google_maps_url": google_enrichment.get("google_maps_url") if google_enrichment else None,
        "price_level": google_enrichment.get("price_level_google") if google_enrichment else None,
        "latitude": lat,
        "longitude": lon,
    }

@search_bp.route('/osm-places', methods=['GET'])
def search_osm_places_route():
    query_term = request.args.get('query', '') # Default to empty string
    location_name = request.args.get('location')
    enrich_google_str = request.args.get('enrich_google', 'false').lower()
    
    try:
        limit = int(request.args.get('limit', 30)) # Default fetch limit from Overpass
        if limit <= 0 or limit > 200: # Max limit for Overpass reasonable fetch
            limit = 30 
    except ValueError:
        limit = 30

    current_app.logger.debug(f"API Call to /osm-places: query='{query_term}', location='{location_name}', enrich_google='{enrich_google_str}', limit={limit}")

    if not location_name:
        return jsonify(message="Missing 'location' parameter.", status="BAD_REQUEST"), 400

    mapped_tags = TAG_MAPPING.get(query_term.lower())
    if not mapped_tags:
        # If query_term was provided but not found in map, and it's not an empty string for default
        if query_term: 
            current_app.logger.warning(f"No direct OSM tag mapping for query: '{query_term}'.")
            return jsonify(message=f"Unsupported query term '{query_term}'. Supported types: {', '.join(k for k in TAG_MAPPING.keys() if k)}", status="UNSUPPORTED_QUERY"), 400
        else: # Empty query term and no "" mapping (though we have one)
            current_app.logger.warning(f"Empty query term received, using default mapping if available or erroring.")
            # This case should be hit by "" in TAG_MAPPING, if not, it's an issue
            return jsonify(message="Query term is required or a default mapping must exist.", status="BAD_REQUEST"), 400

    osm_tag_key, osm_tag_value = mapped_tags
    current_app.logger.info(f"Mapped query '{query_term}' to OSM tags: key='{osm_tag_key}', value='{osm_tag_value}'")

    geo_data = get_coordinates_for_city(location_name)
    if not geo_data or 'bounding_box_str' not in geo_data:
        current_app.logger.info(f"Could not geocode location: '{location_name}'")
        return jsonify(message=f"Could not geocode location: {location_name}", status="LOCATION_NOT_FOUND"), 200

    current_app.logger.info(f"Geocoded '{location_name}' to bbox: {geo_data['bounding_box_str']}")
    
    osm_elements = fetch_osm_data(osm_tag_key, osm_tag_value, geo_data['bounding_box_str'], limit=limit)
    
    if osm_elements is None: # fetch_osm_data now returns [] on error
        current_app.logger.error(f"fetch_osm_data returned None (unexpected error) for {osm_tag_key}={osm_tag_value}.")
        return jsonify(message="Error fetching data from OpenStreetMap/Overpass API.", status="OSM_API_ERROR"), 500
    
    current_app.logger.info(f"Found {len(osm_elements)} raw elements from OSM for {osm_tag_key}={osm_tag_value}.")

    # Filter sparse results
    initial_count = len(osm_elements)
    def is_element_sufficiently_detailed(element):
        tags = element.get("tags", {})
        if not tags.get("name"): return False # Must have a name
        # Add more desired criteria, e.g., must have some address info or contact info
        # has_some_address = tags.get("addr:street") or tags.get("addr:city")
        # has_some_contact = tags.get("phone") or tags.get("website")
        # if not (has_some_address or has_some_contact): return False
        return True
    filtered_osm_elements = [el for el in osm_elements if is_element_sufficiently_detailed(el)]
    current_app.logger.info(f"Filtered from {initial_count} to {len(filtered_osm_elements)} elements after detail check.")

    if not filtered_osm_elements:
        return jsonify(status="ZERO_RESULTS", places=[], message=f"No sufficiently detailed OSM results for '{query_term}' in '{location_name}'."), 200

    processed_leads = []
    # This limit is for how many Google enrichments we attempt in one go for this search.
    # This should be based on user tier in a real application.
    # For now, let's make it small for testing if enrich_google_str is true.
    google_enrich_attempt_limit = 5 if enrich_google_str == 'true' else 0 
    enriched_count = 0
    
    # This processing_limit is how many of the filtered_osm_elements we'll process and send back.
    # Could be same as 'limit' or different if further frontend pagination is desired for a large 'limit'.
    processing_limit = len(filtered_osm_elements) # Process all filtered results for now

    for element in filtered_osm_elements[:processing_limit]:
        google_data_for_this_lead = None
        if enrich_google_str == 'true' and enriched_count < google_enrich_attempt_limit:
            osm_name = element.get("tags", {}).get("name")
            osm_lat = element.get("lat") or element.get("center", {}).get("lat")
            osm_lon = element.get("lon") or element.get("center", {}).get("lon")
            if osm_name and osm_lat and osm_lon:
                # Construct address hint carefully for Google
                osm_address_tags = element.get("tags", {})
                addr_street = osm_address_tags.get("addr:street")
                addr_city_osm = osm_address_tags.get("addr:city")
                address_hint = addr_street
                if addr_city_osm: # If OSM provides city for POI
                    address_hint = f"{addr_street}, {addr_city_osm}" if addr_street else addr_city_osm
                elif geo_data.get('display_name'): # Fallback to city from geocoded location if POI lacks city
                    # Try to extract city from Nominatim's display_name for better context
                    # Example: "Schenectady, Schenectady County, New York, USA" -> "Schenectady"
                    city_context_from_nominatim = geo_data['display_name'].split(',')[0].strip()
                    if address_hint: address_hint += f", {city_context_from_nominatim}"
                    else: address_hint = city_context_from_nominatim

                current_app.logger.debug(f"Attempting Google enrichment for OSM name: '{osm_name}', Address hint: '{address_hint}'")
                google_data_for_this_lead = enrich_with_google_places(osm_name, address=address_hint, latitude=osm_lat, longitude=osm_lon)
                if google_data_for_this_lead:
                    enriched_count += 1
            else:
                current_app.logger.debug(f"Skipping Google enrichment for OSM ID {element.get('id')} (no name/lat/lon).")
        
        normalized_lead = normalize_osm_result(element, google_data_for_this_lead)
        processed_leads.append(normalized_lead)

    # Rank/Sort processed_leads
    def calculate_completeness_score(lead):
        score = 0
        if lead.get("name") and lead["name"] != "Unknown Venue": score += 5
        if lead.get("address"): score += 3
        if lead.get("phone_number"): score += 2
        if lead.get("website"): score += 2
        if lead.get("photo_url"): score += 1 # Google photo
        if lead.get("types") and len(lead.get("types")) > 0: score += 1
        if lead.get("rating"): score +=1 # Google rating
        return score

    if processed_leads:
        processed_leads.sort(key=lambda lead: calculate_completeness_score(lead), reverse=True)
        current_app.logger.info(f"Sorted {len(processed_leads)} leads by completeness score.")
    
    final_message = "OK"
    if not processed_leads:
        final_message = f"No displayable results for '{query_term}' in '{location_name}' after filtering/sorting."
        return jsonify(status="ZERO_RESULTS", places=[], message=final_message, count=0), 200
        
    current_app.logger.info(f"Returning {len(processed_leads)} processed leads. Enriched {enriched_count} with Google.")
    return jsonify(status="OK", places=processed_leads, count=len(processed_leads), message=final_message), 200