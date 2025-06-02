# leadforge_backend/app/routes_search.py
from flask import Blueprint, request, jsonify, current_app
# Assuming utils.py is in the same 'app' directory or one level up and 'app' is the package
# If routes_search.py is in 'app/', use: from .utils import ...
# If your structure is app/routes/search.py and utils.py is in app/utils.py, use: from ..utils import ...
# Based on your ImportError earlier, 'from ..utils import ...' was problematic, so let's assume
# they are sibling modules within the 'app' package, or __init__.py handles it.
# For a typical Flask app structure where 'app' is a package:
from .utils import get_coordinates_for_city, fetch_osm_data, enrich_with_google_places
import time

search_bp = Blueprint('search_bp', __name__) # Matching name from previous HomePage.jsx integration

# OSM Tag Mapping: query_term -> (osm_key, osm_value)
TAG_MAPPING = {
    "bars": ("amenity", "bar"),
    "bar": ("amenity", "bar"), 
    "restaurants": ("amenity", "restaurant"),
    "restaurant": ("amenity", "restaurant"), 
    "cafes": ("amenity", "cafe"),
    "cafe": ("amenity", "cafe"), 
    "breweries": ("craft", "brewery"), # Common tag for craft breweries
    "brewery": ("craft", "brewery"),
    "hotels": ("tourism", "hotel"),
    "hotel": ("tourism", "hotel"),
    "salons": ("shop", "hairdresser"),
    "salon": ("shop", "hairdresser"),
    "gyms": ("leisure", "fitness_centre"),
    "gym": ("leisure", "fitness_centre"),
    "supermarkets": ("shop", "supermarket"),
    "supermarket": ("shop", "supermarket"),
    # Add more, and consider a fallback or default if query_term is empty or not in map
    "": ("amenity", "restaurant") # Example: default to restaurants if query is empty
}

def normalize_osm_result(osm_element, google_enrichment=None):
    """Converts an OSM element and optional Google data into your app's lead format."""
    tags = osm_element.get("tags", {})
    name = (google_enrichment.get("name_google") if google_enrichment 
            else None) or tags.get("name", "Unknown Venue")
    
    addr_parts = [
        tags.get("addr:housenumber"), tags.get("addr:street"),
        tags.get("addr:city"), tags.get("addr:state"), tags.get("addr:postcode")
    ]
    osm_address = ", ".join(filter(None, addr_parts)) or None
    address = (google_enrichment.get("address_google") if google_enrichment 
               else None) or osm_address

    categories = []
    if tags.get("amenity"): categories.append(tags.get("amenity"))
    if tags.get("shop"): categories.append(tags.get("shop"))
    if tags.get("leisure"): categories.append(tags.get("leisure"))
    if tags.get("craft"): categories.append(tags.get("craft"))
    osm_categories_str = ",".join(categories) if categories else None
    
    final_categories = osm_categories_str
    if google_enrichment and google_enrichment.get("types_google"):
        final_categories = ",".join(google_enrichment.get("types_google", []))

    lat = osm_element.get("lat")
    lon = osm_element.get("lon")
    if osm_element.get('type') != 'node' and 'center' in osm_element:
        lat = osm_element['center'].get('lat', lat)
        lon = osm_element['center'].get('lon', lon)

    lead = {
        "osm_id": f"{osm_element.get('type')}/{osm_element.get('id')}",
        "name": name,
        "address": address,
        "latitude": lat,
        "longitude": lon,
        "types_str": final_categories,
        "phone_number": (google_enrichment.get("phone_number_google") if google_enrichment 
                         else None) or tags.get("phone") or tags.get("contact:phone"),
        "website": (google_enrichment.get("website_google") if google_enrichment 
                    else None) or tags.get("website") or tags.get("contact:website"),
        "google_place_id": google_enrichment.get("google_place_id") if google_enrichment else None,
        "photo_url_google": google_enrichment.get("photo_url_google") if google_enrichment else None,
        "rating_google": google_enrichment.get("rating_google") if google_enrichment else None,
        "user_ratings_total_google": google_enrichment.get("user_ratings_total_google") if google_enrichment else None,
        "opening_hours_google": google_enrichment.get("opening_hours_google") if google_enrichment else (tags.get("opening_hours")),
        "google_maps_url": google_enrichment.get("google_maps_url") if google_enrichment else None,
        "business_status_google": google_enrichment.get("business_status_google") if google_enrichment else None,
        "price_level_google": google_enrichment.get("price_level_google") if google_enrichment else None,
        "yelp_id": None,
    }
    return {
        "google_place_id": lead["google_place_id"],
        "osm_id": lead["osm_id"],
        "name": lead["name"],
        "address": lead["address"],
        "website": lead["website"],
        "phone_number": lead["phone_number"],
        "photo_url": lead["photo_url_google"],
        "types": lead["types_str"].split(',') if lead["types_str"] else [],
        "rating": lead["rating_google"],
        "user_ratings_total": lead["user_ratings_total_google"],
        "business_status": lead["business_status_google"],
        "opening_hours": lead["opening_hours_google"],
        "google_maps_url": lead["google_maps_url"],
        "price_level": lead["price_level_google"],
        "latitude": lead["latitude"],
        "longitude": lead["longitude"],
    }

@search_bp.route('/osm-places', methods=['GET'])
def search_osm_places_route():
    query_term = request.args.get('query', '') # Default to empty string if not provided
    location_name = request.args.get('location')
    enrich_google_str = request.args.get('enrich_google', 'false').lower()
    
    # Determine limits (these could be further refined by user tier later)
    # This 'limit' is for how many results to ask Overpass for.
    # Display limits per tier will be handled by frontend or by slicing results later.
    try:
        limit = int(request.args.get('limit', 50)) # Default fetch limit from Overpass
        if limit <=0 or limit > 500: # Sanity check limit
            limit = 50 
    except ValueError:
        limit = 50


    print(f"DEBUG [routes_search]: API Call: query='{query_term}', location='{location_name}', enrich_google='{enrich_google_str}', limit={limit}")

    if not location_name: # Location is mandatory
        return jsonify(message="Missing 'location' parameter.", status="BAD_REQUEST"), 400

    # Use query_term.lower() for mapping, allow empty query_term to hit default in TAG_MAPPING
    mapped_tags = TAG_MAPPING.get(query_term.lower()) 
    if not mapped_tags and query_term: # If query_term was provided but not in map
        print(f"WARNING [routes_search]: No direct OSM tag mapping for query: '{query_term}'. Consider adding to TAG_MAPPING.")
        return jsonify(message=f"Unsupported query term '{query_term}'. Supported types: {', '.join(k for k in TAG_MAPPING.keys() if k)}", status="UNSUPPORTED_QUERY"), 400
    elif not mapped_tags and not query_term: # query_term is empty, and "" not in TAG_MAPPING
         print(f"WARNING [routes_search]: Empty query term and no default in TAG_MAPPING.")
         return jsonify(message=f"Query term is required or a default mapping for empty query must exist.", status="BAD_REQUEST"), 400


    osm_tag_key, osm_tag_value = mapped_tags
    print(f"INFO [routes_search]: Mapped query '{query_term}' to OSM tags: key='{osm_tag_key}', value='{osm_tag_value}'")

    geo_data = get_coordinates_for_city(location_name)
    if not geo_data or 'bounding_box_str' not in geo_data:
        print(f"INFO [routes_search]: Could not geocode location: '{location_name}'")
        return jsonify(message=f"Could not geocode location: {location_name}", status="LOCATION_NOT_FOUND"), 200

    print(f"INFO [routes_search]: Geocoded '{location_name}' to bbox: {geo_data['bounding_box_str']}")
    
    osm_elements = fetch_osm_data(osm_tag_key, osm_tag_value, geo_data['bounding_box_str'], limit=limit)
    
    if osm_elements is None: # Should be [] on error from current fetch_osm_data
        print(f"ERROR [routes_search]: fetch_osm_data issue for {osm_tag_key}={osm_tag_value}.")
        return jsonify(message="Error fetching data from OpenStreetMap/Overpass API.", status="OSM_API_ERROR"), 500
    
    print(f"INFO [routes_search]: Found {len(osm_elements)} raw elements from OSM for {osm_tag_key}={osm_tag_value}.")

    # --- Filter sparse results ---
    initial_count = len(osm_elements)
    def is_element_sufficiently_detailed(element):
        tags = element.get("tags", {})
        if not tags.get("name"): return False
        # Example: require name AND (website OR phone OR a street address part)
        # has_contact = tags.get("website") or tags.get("phone") or tags.get("contact:phone")
        # has_street = tags.get("addr:street")
        # if not (has_contact or has_street):
        #     return False
        return True
    filtered_osm_elements = [el for el in osm_elements if is_element_sufficiently_detailed(el)]
    print(f"INFO [routes_search]: Filtered from {initial_count} to {len(filtered_osm_elements)} elements after detail check.")

    if not filtered_osm_elements:
        return jsonify(status="ZERO_RESULTS", places=[], message=f"No sufficiently detailed OSM results for '{query_term}' in '{location_name}'."), 200

    processed_leads = []
    google_enrich_limit = 10 # Max Google enrichments per API call (could be tier-based)
    enriched_count = 0
    # This display_limit is for how many items to process and send to frontend.
    # Frontend will handle its own per-page view limits (RESULTS_PER_VIEW) and free tier limits (NON_PRO_VISIBLE_LIMIT).
    # Backend sends up to this many potentially enrichable items.
    backend_processing_limit = limit # Process up to the number of items fetched from OSM

    for element in filtered_osm_elements[:backend_processing_limit]: # Process only up to the processing limit
        google_data_for_this_lead = None
        if enrich_google_str == 'true' and enriched_count < google_enrich_limit: # (Add tier check here later for who can enrich)
            osm_name = element.get("tags", {}).get("name")
            osm_lat = element.get("lat") or element.get("center", {}).get("lat")
            osm_lon = element.get("lon") or element.get("center", {}).get("lon")
            if osm_name and osm_lat and osm_lon:
                addr_street = element.get("tags", {}).get("addr:street")
                addr_city_osm = element.get("tags", {}).get("addr:city")
                address_hint_for_google = addr_street
                if addr_city_osm and addr_street: address_hint_for_google = f"{addr_street}, {addr_city_osm}"
                elif addr_city_osm: address_hint_for_google = addr_city_osm
                
                if not address_hint_for_google or not addr_city_osm: # If city part of address is weak from OSM tags
                    original_loc_city_part = location_name.split(',')[0].strip() # Use city from original query
                    if address_hint_for_google: address_hint_for_google += f", {original_loc_city_part}"
                    else: address_hint_for_google = location_name # Fallback to full original location

                print(f"DEBUG [routes_search]: Attempting Google enrichment for OSM name: '{osm_name}', Address hint: '{address_hint_for_google}'")
                google_data_for_this_lead = enrich_with_google_places(osm_name, address=address_hint_for_google, latitude=osm_lat, longitude=osm_lon)
                if google_data_for_this_lead:
                    enriched_count += 1
            else:
                print(f"DEBUG [routes_search]: Skipping Google enrichment for OSM ID {element.get('id')} (no name/lat/lon).")
        
        normalized_lead = normalize_osm_result(element, google_data_for_this_lead)
        processed_leads.append(normalized_lead)

    # --- Rank/Sort processed_leads ---
    def calculate_completeness_score(lead):
        score = 0
        if lead.get("name") and lead["name"] != "Unknown Venue": score += 5
        if lead.get("address"): score += 3
        if lead.get("phone_number"): score += 2
        if lead.get("website"): score += 2
        if lead.get("photo_url"): score += 1 # From Google
        if lead.get("types") and len(lead.get("types")) > 0: score += 1
        if lead.get("rating"): score +=1 # From Google
        # Consider number of OSM tags element.get("tags") had before normalization
        return score

    if processed_leads:
        processed_leads.sort(key=lambda lead: calculate_completeness_score(lead), reverse=True)
        print(f"INFO [routes_search]: Sorted {len(processed_leads)} leads by completeness score.")
    
    final_message = "OK"
    if not processed_leads: # If after all processing, list is empty
        final_message = f"No displayable results for '{query_term}' in '{location_name}' after filtering/sorting."
        return jsonify(status="ZERO_RESULTS", places=[], message=final_message, count=0), 200

    # Frontend will handle its own slicing for display (NON_PRO_VISIBLE_LIMIT, RESULTS_PER_VIEW)
    # Backend sends all processed & sorted leads up to backend_processing_limit
    print(f"INFO [routes_search]: Returning {len(processed_leads)} processed leads. Enriched {enriched_count} with Google.")
    return jsonify(status="OK", places=processed_leads, count=len(processed_leads), message=final_message), 200