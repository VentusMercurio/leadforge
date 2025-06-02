# leadforge_backend/app/routes_search.py
from flask import Blueprint, request, jsonify, current_app
# Ensure correct relative import for utils. If utils.py is in the same 'app/' dir:
from .utils import get_coordinates_for_city, fetch_osm_data, enrich_with_google_places
import time

search_bp = Blueprint('search_bp', __name__)

# --- EXPANDED OSM Tag Mapping: user_query_term -> list of (osm_key, osm_value) tuples ---
TAG_MAPPING = {
    # Food & Drink
    "restaurants": [("amenity", "restaurant")],
    "restaurant": [("amenity", "restaurant")],
    "food": [
        ("amenity", "restaurant"), ("amenity", "cafe"), ("amenity", "fast_food"),
        ("amenity", "food_court"), ("shop", "bakery"), ("shop", "deli"),
        ("shop", "ice_cream"), ("shop", "pastry"), 
        # ("cuisine", "*") # This can be very broad, use with caution or higher limits
    ],
    "cafes": [("amenity", "cafe"), ("shop", "coffee")],
    "cafe": [("amenity", "cafe"), ("shop", "coffee")],
    "bars": [("amenity", "bar"), ("amenity", "pub")],
    "bar": [("amenity", "bar"), ("amenity", "pub")],
    "pubs": [("amenity", "pub"), ("amenity", "bar")],
    "pub": [("amenity", "pub"), ("amenity", "bar")],
    "nightclubs": [("amenity", "nightclub"), ("leisure", "dance")],
    "nightclub": [("amenity", "nightclub"), ("leisure", "dance")],
    "breweries": [("craft", "brewery"), ("microbrewery", "yes"), ("industrial", "brewery")],
    "brewery": [("craft", "brewery"), ("microbrewery", "yes"), ("industrial", "brewery")],
    "wineries": [("craft", "winery"), ("shop", "wine"), ("tourism", "winery")],
    "liquor stores": [("shop", "alcohol"), ("shop", "wine"), ("shop", "beer")],
    "fast food": [("amenity", "fast_food")],
    "bakeries": [("shop", "bakery")],
    "ice cream shops": [("shop", "ice_cream"), ("amenity", "ice_cream")],
    "pizza places": [("amenity", "restaurant"),("cuisine","pizza")], # Example of AND: will need utils change

    # Retail & Shopping
    "shops": [("shop", "*")], # WARNING: Potentially very broad results
    "supermarkets": [("shop", "supermarket"), ("shop", "grocery")],
    "grocery stores": [("shop", "grocery"), ("shop", "supermarket"), ("shop", "convenience")],
    "convenience stores": [("shop", "convenience")],
    "clothing stores": [("shop", "clothes"), ("shop", "fashion"), ("shop", "boutique"), ("shop", "apparel")],
    "shoe stores": [("shop", "shoes")],
    "bookstores": [("shop", "books")],
    "electronics stores": [("shop", "electronics"), ("shop", "computer"), ("shop", "mobile_phone")],
    "hardware stores": [("shop", "hardware"), ("shop", "doityourself")],
    "pharmacies": [("amenity", "pharmacy"), ("shop", "chemist")],
    "florists": [("shop", "florist")],
    "gift shops": [("shop", "gift"), ("shop", "souvenir")],
    "malls": [("shop", "mall")],
    "department stores": [("shop", "department_store")],
    "furniture stores": [("shop", "furniture")],
    "jewelry stores": [("shop", "jewelry")],
    "toy stores": [("shop", "toys")],
    "pet stores": [("shop", "pet")],
    "bike shops": [("shop", "bicycle")],
    "car dealerships": [("shop", "car")],
    "opticians": [("shop", "optician")],

    # Accommodation
    "hotels": [("tourism", "hotel")],
    "hotel": [("tourism", "hotel")],
    "motels": [("tourism", "motel")],
    "hostels": [("tourism", "hostel")],
    "guesthouses": [("tourism", "guest_house"), ("tourism", "bed_and_breakfast")],
    "apartments": [("tourism", "apartment")], # For short-term rentals if tagged

    # Services
    "salons": [("shop", "hairdresser"), ("shop", "beauty")],
    "hair salons": [("shop", "hairdresser")],
    "barbershops": [("shop", "barber")],
    "beauty salons": [("shop", "beauty"), ("shop", "nails")],
    "spas": [("leisure", "spa"), ("shop", "spa")],
    "laundromats": [("shop", "laundry"), ("shop", "launderette")],
    "dry cleaning": [("shop", "dry_cleaning")],
    "banks": [("amenity", "bank")],
    "atms": [("amenity", "atm")],
    "post offices": [("amenity", "post_office")],
    "car repair": [("shop", "car_repair"), ("shop", "car_parts")],
    "gas stations": [("amenity", "fuel")],
    "real estate agencies": [("office", "estate_agent")],
    "travel agencies": [("office", "travel_agent")],
    "car wash": [("amenity", "car_wash")],
    "parking": [("amenity", "parking")],
    "libraries": [("amenity", "library")],

    # Health & Wellness
    "gyms": [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    "fitness centers": [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    "yoga studios": [("leisure", "fitness_centre"), ("sport", "yoga"), ("leisure","yoga")],
    "doctors": [("amenity", "doctors"), ("amenity", "clinic"), ("healthcare","doctor")],
    "dentists": [("amenity", "dentist"), ("healthcare","dentist")],
    "hospitals": [("amenity", "hospital"),("healthcare","hospital")],
    "clinics": [("amenity", "clinic"),("healthcare","clinic")],
    "veterinarians": [("amenity", "veterinary"),("shop","pet"),("healthcare","veterinary")],

    # Entertainment & Leisure
    "cinemas": [("amenity", "cinema")],
    "movie theaters": [("amenity", "cinema")],
    "theaters": [("amenity", "theatre")], # Live performance
    "live music venues": [("leisure", "live_music_venue"), ("amenity", "music_venue")],
    "museums": [("tourism", "museum")],
    "art galleries": [("tourism", "gallery"), ("shop", "art")],
    "parks": [("leisure", "park"), ("leisure", "garden"), ("boundary", "national_park"), ("boundary", "protected_area")],
    "playgrounds": [("leisure", "playground")],
    "bowling alleys": [("leisure", "bowling_alley")],
    "arcades": [("leisure", "amusement_arcade")],
    "zoos": [("tourism", "zoo")],
    "aquariums": [("tourism", "aquarium")],
    "stadiums": [("leisure", "stadium"), ("sport","stadium")],
    "beaches": [("natural", "beach"), ("leisure","beach_resort")],

    # Transportation
    "airports": [("aeroway", "aerodrome"), ("amenity", "airport")],
    "train stations": [("railway", "station"), ("public_transport", "station")],
    "bus stops": [("highway", "bus_stop"), ("public_transport", "platform")],
    "taxi stands": [("amenity", "taxi")],
    "ferry terminals": [("amenity", "ferry_terminal")],

    # Default / Fallback
    "": [("amenity", "restaurant"), ("shop", "*")] # Default if no query term
}
# --- END EXPANDED TAG_MAPPING ---


# --- normalize_osm_result function (keep your existing one or the last version we worked on) ---
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
    query_term = request.args.get('query', '').strip().lower() # Normalize to lowercase
    location_name = request.args.get('location')
    enrich_google_str = request.args.get('enrich_google', 'false').lower()
    
    try:
        limit = int(request.args.get('limit', 50)) 
        if limit <= 0 or limit > 500: limit = 50 # Cap limit for Overpass performance
    except ValueError:
        limit = 50

    current_app.logger.debug(f"API Call to /osm-places: query='{query_term}', location='{location_name}', enrich_google='{enrich_google_str}', limit={limit}")

    if not location_name:
        return jsonify(message="Missing 'location' parameter.", status="BAD_REQUEST"), 400

    # --- MODIFIED TAG MAPPING LOGIC ---
    osm_tag_conditions_list = TAG_MAPPING.get(query_term) # query_term is already lowercased

    if not osm_tag_conditions_list:
        if query_term: # If a specific query was given but not in map, search by name
            current_app.logger.info(f"Query term '{query_term}' not in TAG_MAPPING. Defaulting to name search.")
            # This creates a list of tuples, just like TAG_MAPPING provides
            osm_tag_conditions_list = [("name", query_term)] # Case-sensitive name search by default
            # For case-insensitive name search with regex, Overpass syntax is different:
            # osm_tag_conditions_list = [("name~", f"^{query_term}$", "i")] # Example, fetch_osm_data needs to handle regex flag
        else: # Empty query term was not caught by "" in TAG_MAPPING (shouldn't happen if "" is a key)
            current_app.logger.warning(f"Empty query term and no default mapping found.")
            return jsonify(message="Query term is required or a default mapping must exist.", status="BAD_REQUEST"), 400
    # --- END MODIFIED TAG MAPPING LOGIC ---
            
    current_app.logger.info(f"Using OSM tag conditions for '{query_term}': {osm_tag_conditions_list}")

    geo_data = get_coordinates_for_city(location_name)
    if not geo_data or 'bounding_box_str' not in geo_data:
        current_app.logger.info(f"Could not geocode location: '{location_name}'")
        return jsonify(message=f"Could not geocode location: {location_name}", status="LOCATION_NOT_FOUND"), 200

    current_app.logger.info(f"Geocoded '{location_name}' to bbox: {geo_data['bounding_box_str']}")
    
    # Pass the list of tag conditions to fetch_osm_data
    osm_elements = fetch_osm_data(osm_tag_conditions_list, geo_data['bounding_box_str'], limit=limit)
    
    if osm_elements is None: 
        current_app.logger.error(f"fetch_osm_data returned None for query '{query_term}'.")
        return jsonify(message="Error fetching data from OpenStreetMap/Overpass API.", status="OSM_API_ERROR"), 500
    
    current_app.logger.info(f"Found {len(osm_elements)} raw elements from OSM for query '{query_term}'.")

    # --- Filter sparse results (your existing logic) ---
    initial_count = len(osm_elements)
    def is_element_sufficiently_detailed(element):
        tags = element.get("tags", {})
        if not tags.get("name"): return False
        return True
    filtered_osm_elements = [el for el in osm_elements if is_element_sufficiently_detailed(el)]
    current_app.logger.info(f"Filtered from {initial_count} to {len(filtered_osm_elements)} elements after detail check.")

    if not filtered_osm_elements:
        return jsonify(status="ZERO_RESULTS", places=[], message=f"No sufficiently detailed OSM results for '{query_term}' in '{location_name}'."), 200

    # --- Processing, Enrichment, Sorting (your existing logic) ---
    processed_leads = []
    google_enrich_attempt_limit = 5 if enrich_google_str == 'true' else 0 
    enriched_count = 0
    backend_processing_limit = limit 

    for element in filtered_osm_elements[:backend_processing_limit]:
        google_data_for_this_lead = None
        if enrich_google_str == 'true' and enriched_count < google_enrich_attempt_limit:
            osm_name = element.get("tags", {}).get("name")
            osm_lat = element.get("lat") or element.get("center", {}).get("lat")
            osm_lon = element.get("lon") or element.get("center", {}).get("lon")
            if osm_name and osm_lat and osm_lon:
                # ... (Address hint logic - keep your existing refined version) ...
                osm_address_tags = element.get("tags", {})
                addr_street = osm_address_tags.get("addr:street")
                addr_city_osm = osm_address_tags.get("addr:city")
                address_hint = addr_street
                if addr_city_osm: address_hint = f"{addr_street}, {addr_city_osm}" if addr_street else addr_city_osm
                elif geo_data.get('display_name'):
                    city_context_from_nominatim = geo_data['display_name'].split(',')[0].strip()
                    if address_hint: address_hint += f", {city_context_from_nominatim}"
                    else: address_hint = city_context_from_nominatim
                else: # Fallback if no other address info
                    address_hint = location_name

                current_app.logger.debug(f"Attempting Google enrichment for OSM name: '{osm_name}', Address hint: '{address_hint}'")
                google_data_for_this_lead = enrich_with_google_places(osm_name, address=address_hint, latitude=osm_lat, longitude=osm_lon)
                if google_data_for_this_lead:
                    enriched_count += 1
        
        normalized_lead = normalize_osm_result(element, google_data_for_this_lead)
        processed_leads.append(normalized_lead)

    def calculate_completeness_score(lead): # Keep your existing scoring
        score = 0 # ... (your scoring logic) ...
        if lead.get("name") and lead["name"] != "Unknown Venue": score += 5
        if lead.get("address"): score += 3
        if lead.get("phone_number"): score += 2
        if lead.get("website"): score += 2
        return score
    if processed_leads:
        processed_leads.sort(key=lambda lead: calculate_completeness_score(lead), reverse=True)
    
    final_message = "OK"
    if not processed_leads:
        final_message = f"No displayable results for '{query_term}' in '{location_name}' after filtering/sorting."
        return jsonify(status="ZERO_RESULTS", places=[], message=final_message, count=0), 200
        
    current_app.logger.info(f"Returning {len(processed_leads)} processed leads. Enriched {enriched_count} with Google.")
    return jsonify(status="OK", places=processed_leads, count=len(processed_leads), message=final_message), 200