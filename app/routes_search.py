# app/routes_search.py
# app/routes_search.py
from flask import Blueprint, request, jsonify, current_app
# Ensure utils are imported from the correct relative path
from .utils import get_coordinates_for_city, fetch_osm_data, enrich_with_google_places # <--- CORRECTED IMPORT
import time

# search_bp = Blueprint('search', __name__, url_prefix='/api/search') # Original
# If your __init__.py registers search_bp with url_prefix='/api/search', then it's fine here.
# Or, ensure the prefix is consistent. Let's assume it's correctly registered in __init__.
search_bp = Blueprint('search_bp', __name__) # Name changed to match your previous init

# OSM Tag Mapping: query_term -> (osm_key, osm_value)
TAG_MAPPING = {
    "bars": ("amenity", "bar"),
    "restaurants": ("amenity", "restaurant"),
    "cafes": ("amenity", "cafe"),
    "breweries": ("craft", "brewery"), # Common tag for craft breweries
    "hotels": ("tourism", "hotel"),
    "salons": ("shop", "hairdresser"),
    "gyms": ("leisure", "fitness_centre"),
    "supermarkets": ("shop", "supermarket"),
    # Add more mappings
}

def normalize_osm_result(osm_element, google_enrichment=None):
    """Converts an OSM element and optional Google data into your app's lead format."""
    tags = osm_element.get("tags", {})
    # Prefer Google's name if enriched, otherwise OSM name
    name = (google_enrichment.get("name_google") if google_enrichment 
            else None) or tags.get("name", "Unknown Venue")
    
    addr_parts = [
        tags.get("addr:housenumber"), tags.get("addr:street"),
        tags.get("addr:city"), tags.get("addr:state"), tags.get("addr:postcode")
    ]
    osm_address = ", ".join(filter(None, addr_parts)) or None
    # Prefer Google's address if enriched
    address = (google_enrichment.get("address_google") if google_enrichment 
               else None) or osm_address

    categories = []
    if tags.get("amenity"): categories.append(tags.get("amenity"))
    if tags.get("shop"): categories.append(tags.get("shop"))
    if tags.get("leisure"): categories.append(tags.get("leisure"))
    if tags.get("craft"): categories.append(tags.get("craft"))
    # ... add more relevant tags
    # If enriched, you might want to use or merge google_types
    osm_categories_str = ",".join(categories) if categories else None
    
    final_categories = osm_categories_str
    if google_enrichment and google_enrichment.get("types_google"):
        # Example: merge and deduplicate categories
        # combined_cats = list(set(categories + google_enrichment.get("types_google", [])))
        # final_categories = ",".join(combined_cats) if combined_cats else osm_categories_str
        final_categories = ",".join(google_enrichment.get("types_google", [])) # Or prioritize Google types


    # Latitude/Longitude: from OSM node directly, or center for ways/relations
    lat = osm_element.get("lat")
    lon = osm_element.get("lon")
    if osm_element.get('type') != 'node' and 'center' in osm_element:
        lat = osm_element['center'].get('lat', lat) # Fallback to node lat if center missing
        lon = osm_element['center'].get('lon', lon) # Fallback to node lon if center missing

    lead = {
        "osm_id": f"{osm_element.get('type')}/{osm_element.get('id')}",
        "name": name,
        "address": address,
        "latitude": lat,
        "longitude": lon,
        "types_str": final_categories, # Store as string, frontend can split
        "phone_number": (google_enrichment.get("phone_number_google") if google_enrichment 
                         else None) or tags.get("phone") or tags.get("contact:phone"),
        "website": (google_enrichment.get("website_google") if google_enrichment 
                    else None) or tags.get("website") or tags.get("contact:website"),
        
        # Google specific fields (populated if enriched)
        "google_place_id": google_enrichment.get("google_place_id") if google_enrichment else None,
        "photo_url_google": google_enrichment.get("photo_url_google") if google_enrichment else None,
        "rating_google": google_enrichment.get("rating_google") if google_enrichment else None,
        "user_ratings_total_google": google_enrichment.get("user_ratings_total_google") if google_enrichment else None,
        "opening_hours_google": google_enrichment.get("opening_hours_google") if google_enrichment else (tags.get("opening_hours")), # OSM opening_hours is complex
        "google_maps_url": google_enrichment.get("google_maps_url") if google_enrichment else None,
        "business_status_google": google_enrichment.get("business_status_google") if google_enrichment else None,
        "price_level_google": google_enrichment.get("price_level_google") if google_enrichment else None,

        # Yelp placeholders
        "yelp_id": None,
    }

    # Map to a "search result" structure, can be different from SavedLead model to_dict
    # This structure should be what your frontend expects for displaying search results.
    return {
        "google_place_id": lead["google_place_id"],
        "osm_id": lead["osm_id"], # Good to keep for debugging or future use
        "name": lead["name"],
        "address": lead["address"],
        "website": lead["website"],
        "phone_number": lead["phone_number"],
        "photo_url": lead["photo_url_google"], # Primary photo source
        "types": lead["types_str"].split(',') if lead["types_str"] else [],
        "rating": lead["rating_google"],
        "user_ratings_total": lead["user_ratings_total_google"],
        "business_status": lead["business_status_google"],
        "opening_hours": lead["opening_hours_google"],
        "google_maps_url": lead["google_maps_url"],
        "price_level": lead["price_level_google"],
        # For display in search results, lat/lon might be useful for a map
        "latitude": lead["latitude"],
        "longitude": lead["longitude"],
    }


@search_bp.route('/osm-places', methods=['GET'])
def search_osm_places_route():
    query_term = request.args.get('query')
    location_name = request.args.get('location')
    enrich_google_str = request.args.get('enrich_google', 'false').lower()
    limit = request.args.get('limit', type=int, default=20) # Default result limit from OSM

    print(f"DEBUG [routes_search]: API Call: query='{query_term}', location='{location_name}', enrich_google='{enrich_google_str}', limit={limit}")

    if not query_term or not location_name:
        return jsonify(message="Missing 'query' and/or 'location' parameters.", status="BAD_REQUEST"), 400

    mapped_tags = TAG_MAPPING.get(query_term.lower())
    if not mapped_tags:
        # Fallback: if no direct tag, try searching by name as a tag
        # This is often less effective for categories but can find specific named places.
        # Or, return an error indicating unsupported query.
        print(f"WARNING [routes_search]: No direct OSM tag mapping for query: '{query_term}'. Consider adding to TAG_MAPPING or searching by name if appropriate.")
        # osm_tag_key, osm_tag_value = "name", query_term # Example: search for name="query_term"
        # For now, let's be strict and require a mapped tag for category search.
        return jsonify(message=f"Unsupported query term '{query_term}'. Supported types: {', '.join(TAG_MAPPING.keys())}", status="UNSUPPORTED_QUERY"), 400
        
    osm_tag_key, osm_tag_value = mapped_tags
    print(f"INFO [routes_search]: Mapped query '{query_term}' to OSM tags: key='{osm_tag_key}', value='{osm_tag_value}'")

    geo_data = get_coordinates_for_city(location_name)
    if not geo_data or 'bounding_box_str' not in geo_data: # Ensure 'bounding_box_str' is the key from utils
        print(f"INFO [routes_search]: Could not geocode location: '{location_name}'")
        return jsonify(message=f"Could not geocode location: {location_name}", status="LOCATION_NOT_FOUND"), 200 # 200 as per previous ZERO_RESULTS

    print(f"INFO [routes_search]: Geocoded '{location_name}' to bbox: {geo_data['bounding_box_str']}")
    
    # Fetch from OSM
    osm_elements = fetch_osm_data(osm_tag_key, osm_tag_value, geo_data['bounding_box_str'], limit=limit)
    
    if osm_elements is None: # fetch_osm_data returns [] on error now, None was old. Keeping check for safety.
        print(f"ERROR [routes_search]: fetch_osm_data returned None, indicating an issue during fetch for {osm_tag_key}={osm_tag_value}.")
        return jsonify(message="Error fetching data from OpenStreetMap/Overpass API.", status="OSM_API_ERROR"), 500
    
    print(f"INFO [routes_search]: Found {len(osm_elements)} raw elements from OSM for {osm_tag_key}={osm_tag_value}.")

    if not osm_elements:
        return jsonify(status="ZERO_RESULTS", places=[], message=f"No OSM results for '{query_term}' in '{location_name}'."), 200

    processed_leads = []
    # Limit how many Google enrichments to do per search to control cost/time
    google_enrich_limit = 10 # Max enrichments per call
    enriched_count = 0

    for element in osm_elements:
        # Basic filter: skip if no tags or no name tag (can be adjusted)
        if "tags" not in element or not element["tags"].get("name"):
            print(f"DEBUG [routes_search]: Skipping OSM element {element.get('type')}/{element.get('id')} due to missing tags or name.")
            continue

        google_data_for_this_lead = None
        if enrich_google_str == 'true' and enriched_count < google_enrich_limit:
            osm_name = element["tags"]["name"]
            osm_lat = element.get("lat") or element.get("center", {}).get("lat")
            osm_lon = element.get("lon") or element.get("center", {}).get("lon")

            if osm_name and osm_lat and osm_lon:
                # Construct a more specific address hint for Google if possible
                osm_address_tags = element.get("tags", {})
                addr_street = osm_address_tags.get("addr:street")
                addr_city_osm = osm_address_tags.get("addr:city") # Nominatim gives overall city
                address_hint_for_google = addr_street
                if addr_city_osm and addr_street: # If both street and city from OSM tags
                    address_hint_for_google = f"{addr_street}, {addr_city_osm}"
                elif addr_city_osm: # If only city from OSM tags
                    address_hint_for_google = addr_city_osm
                
                # Include original location_name (e.g., "Albany NY") if no specific city from OSM tags
                # This helps Google if OSM data is sparse on city level for the POI
                if not address_hint_for_google or not addr_city_osm:
                    if address_hint_for_google: # e.g. street exists, but no city tag on POI
                        address_hint_for_google += f", {location_name.split(',')[0].strip()}" # Add city from original query
                    else: # No street or city tag on POI
                        # If we have a display_name from Nominatim for the overall area, use parts of it
                        # geo_data['display_name'] could be "Albany, Albany County, New York, United States"
                        # Using the original location_name might be simpler here.
                        address_hint_for_google = location_name


                print(f"DEBUG [routes_search]: Attempting Google enrichment for OSM name: '{osm_name}', Address hint: '{address_hint_for_google}'")
                google_data_for_this_lead = enrich_with_google_places(
                    osm_name, 
                    address=address_hint_for_google,
                    latitude=osm_lat,
                    longitude=osm_lon
                )
                if google_data_for_this_lead:
                    enriched_count += 1
                # Consider a small delay if making many Google API calls rapidly, though utils.py has none
                # time.sleep(0.05) # 50ms
            else:
                print(f"DEBUG [routes_search]: Skipping Google enrichment for OSM ID {element.get('id')} due to missing name or lat/lon from OSM element.")
        
        normalized_lead = normalize_osm_result(element, google_data_for_this_lead)
        processed_leads.append(normalized_lead)
        
        # Optional: if you want to cap total results returned even if OSM returns more
        # if len(processed_leads) >= some_max_display_limit:
        #     break

    print(f"INFO [routes_search]: Returning {len(processed_leads)} processed leads. Enriched {enriched_count} with Google.")
    return jsonify(status="OK", places=processed_leads, count=len(processed_leads)), 200