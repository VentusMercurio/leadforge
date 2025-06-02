# app/utils.py
import requests
from flask import current_app # For accessing app config and extensions like cache
import time # Keep for potential future rate limiting needs

# Define cache timeouts (in seconds) at the module level for clarity
FIND_PLACE_CACHE_TIMEOUT = 3600 * 24     # Cache Place ID result for 1 day
PLACE_DETAILS_CACHE_TIMEOUT = 3600 * 6 # Cache full details for 6 hours
NOMINATIM_CACHE_TIMEOUT = 3600 * 24 * 7  # Cache geocoding results for 1 week

def get_coordinates_for_city(city_name):
    """Geocodes a city name to latitude, longitude, and bounding box using Nominatim, with caching."""
    cache = current_app.extensions.get('cache')
    nominatim_cache_key = f"nominatim_coords:{city_name.lower().replace(' ', '_').replace(',', '')}"

    if cache:
        cached_data = cache.get(nominatim_cache_key)
        if cached_data:
            print(f"DEBUG [get_coordinates_for_city]: Cache HIT for '{city_name}' (Key: {nominatim_cache_key})")
            return cached_data

    print(f"DEBUG [get_coordinates_for_city]: Cache MISS for '{city_name}' (Key: {nominatim_cache_key}). Calling Nominatim API.")
    nominatim_url = current_app.config.get('NOMINATIM_API_URL')
    if not nominatim_url:
        print("ERROR [get_coordinates_for_city]: Nominatim API URL not configured.")
        return None

    headers = {'User-Agent': current_app.config.get('NOMINATIM_USER_AGENT', 'LeadForgeApp/0.1 contact@example.com')}
    params = {'q': city_name, 'format': 'json', 'limit': 1, 'addressdetails': 1}
    
    print(f"DEBUG [get_coordinates_for_city]: Requesting Nominatim: {nominatim_url} with params: {params}")
    try:
        # Consider adding time.sleep(1.1) here if making many *uncached* calls rapidly
        response = requests.get(nominatim_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"DEBUG [get_coordinates_for_city]: Nominatim raw response data (first 500 chars): {str(data)[:500]}")
        if data and len(data) > 0:
            location_data = data[0]
            bbox_nominatim = location_data.get('boundingbox') # [south, north, west, east]
            if bbox_nominatim and len(bbox_nominatim) == 4:
                bbox_overpass_coords_only = f"{bbox_nominatim[0]},{bbox_nominatim[2]},{bbox_nominatim[1]},{bbox_nominatim[3]}" # south,west,north,east
                result = {
                    'latitude': float(location_data.get('lat')),
                    'longitude': float(location_data.get('lon')),
                    'bounding_box_str': bbox_overpass_coords_only,
                    'display_name': location_data.get('display_name')
                }
                if cache:
                    cache.set(nominatim_cache_key, result, timeout=NOMINATIM_CACHE_TIMEOUT)
                    print(f"DEBUG [get_coordinates_for_city]: Cached coordinates for '{city_name}'")
                return result
            else:
                print(f"WARNING [get_coordinates_for_city]: Bounding box not found/incomplete for '{city_name}': {bbox_nominatim}")
        else:
            print(f"WARNING [get_coordinates_for_city]: No data returned from Nominatim for '{city_name}'")
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR [get_coordinates_for_city]: Nominatim API HTTP error for {city_name}: {http_err} - Response: {response.text if 'response' in locals() else 'N/A'}")
    except requests.exceptions.RequestException as e:
        print(f"ERROR [get_coordinates_for_city]: Nominatim API request error for {city_name}: {e}")
    except Exception as e:
        print(f"ERROR [get_coordinates_for_city]: Error processing Nominatim response for {city_name}: {e}")
    return None


def fetch_osm_data(osm_tag_key, osm_tag_value, bounding_box_str, limit=20, osm_object_types=("node", "way", "relation")):
    """Fetches data from Overpass API. Caching Overpass results can be complex due to query variability, so not implemented here by default."""
    overpass_url = current_app.config.get('OVERPASS_API_URL')
    if not overpass_url:
        print("ERROR [fetch_osm_data]: Overpass API URL not configured.")
        return [] 
    query_parts = []
    for obj_type in osm_object_types:
        query_parts.append(f'{obj_type}["{osm_tag_key}"="{osm_tag_value}"]({bounding_box_str});')
    timeout_seconds = 30
    overpass_query = f"""\
    [out:json][timeout:{timeout_seconds}];
    (
      {''.join(query_parts)}
    );
    out center {limit}; 
    """
    print(f"DEBUG [fetch_osm_data]: Constructed Overpass Query:\n{overpass_query}")
    print(f"DEBUG [fetch_osm_data]: Posting to Overpass URL: {overpass_url}")
    try:
        response = requests.post(overpass_url, data={'data': overpass_query}, headers={'User-Agent': current_app.config.get('APP_USER_AGENT', 'LeadForgeApp/0.1')}, timeout=timeout_seconds + 5)
        response.raise_for_status()
        data = response.json()
        print(f"DEBUG [fetch_osm_data]: Raw Overpass JSON response (first 500 chars): {str(data)[:500]}")
        elements = data.get('elements', [])
        print(f"DEBUG [fetch_osm_data]: Overpass response elements count: {len(elements)}")
        return elements
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR [fetch_osm_data]: Overpass API HTTP error: {http_err} - Status: {response.status_code if 'response' in locals() else 'N/A'} - Response: {response.text if 'response' in locals() else 'N/A'}")
    except requests.exceptions.Timeout:
        print(f"ERROR [fetch_osm_data]: Overpass API request timed out after {timeout_seconds + 5} seconds.")
    except requests.exceptions.RequestException as e:
        print(f"ERROR [fetch_osm_data]: Overpass API request error: {e}")
    except Exception as e:
        print(f"ERROR [fetch_osm_data]: Error processing Overpass response: {e}")
    return []


def enrich_with_google_places(business_name, address=None, latitude=None, longitude=None, known_place_id=None):
    """
    Finds a place on Google and get its details, using caching.
    Can optionally take a known_place_id to skip the "Find Place" step.
    """
    cache = current_app.extensions.get('cache') # Get cache instance
    if not cache:
        print("ERROR [enrich_with_google_places]: Cache not available. Proceeding without caching.")

    api_key = current_app.config.get('GOOGLE_PLACES_API_KEY')
    if not api_key:
        print("WARNING [enrich_with_google_places]: Google Places API key not configured.")
        return None

    place_id_to_use = known_place_id
    
    if not place_id_to_use:
        find_place_cache_key_parts = [
            "gfind_pid", str(business_name or "").lower().strip().replace(" ", "_"),
            str(address or "").lower().strip().replace(" ", "_").replace(",", ""),
            str(round(latitude, 3)) if latitude is not None else "none",
            str(round(longitude, 3)) if longitude is not None else "none"
        ]
        find_place_cache_key = ":".join(part for part in find_place_cache_key_parts if part)
        
        cached_place_id = None
        if cache: cached_place_id = cache.get(find_place_cache_key)
        
        if cached_place_id:
            print(f"DEBUG [enrich_with_google_places]: Cache HIT for Find Place ID: {cached_place_id} (Key: {find_place_cache_key})")
            place_id_to_use = cached_place_id
        else:
            print(f"DEBUG [enrich_with_google_places]: Cache MISS for Find Place ID (Key: {find_place_cache_key}). Calling Find Place API.")
            find_place_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
            input_query = business_name
            if address: input_query += f", {address}"
            find_params = {"input": input_query, "inputtype": "textquery", "fields": "place_id,name", "key": api_key}
            if latitude and longitude: find_params["locationbias"] = f"circle:2000@{latitude},{longitude}"
            try:
                find_response = requests.get(find_place_url, params=find_params, timeout=10)
                find_response.raise_for_status()
                find_data = find_response.json()
                print(f"DEBUG [enrich_with_google_places]: Google Find Place raw response: {str(find_data)[:300]}")
                if find_data.get("status") == "OK" and find_data.get("candidates"):
                    place_id_to_use = find_data["candidates"][0].get("place_id")
                    if place_id_to_use and cache:
                        cache.set(find_place_cache_key, place_id_to_use, timeout=FIND_PLACE_CACHE_TIMEOUT)
                        print(f"DEBUG [enrich_with_google_places]: Found and cached Place ID: {place_id_to_use}")
                elif find_data.get("status") != "OK":
                    print(f"WARNING [enrich_with_google_places]: Google Find Place status not OK: {find_data.get('status')} for '{business_name}'. Error: {find_data.get('error_message')}")
            except Exception as e: # Catching a broader range of request/parsing errors
                print(f"ERROR [enrich_with_google_places]: Google Find Place API call/processing error for '{business_name}': {e}")
                return None 

    if not place_id_to_use:
        print(f"DEBUG [enrich_with_google_places]: No Google Place ID found or determined for '{business_name}'.")
        return None

    details_cache_key = f"gdetails_v2:{place_id_to_use}"
    cached_details_result = None
    if cache: cached_details_result = cache.get(details_cache_key)
    
    if cached_details_result:
        print(f"DEBUG [enrich_with_google_places]: Cache HIT for Place Details ID: {place_id_to_use}")
        return cached_details_result

    print(f"DEBUG [enrich_with_google_places]: Cache MISS for Place Details ID: {place_id_to_use}. Calling Details API.")
    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
    details_fields = "place_id,name,formatted_address,international_phone_number,website,opening_hours,price_level,rating,user_ratings_total,photos,url,business_status,types,vicinity,utc_offset"
    details_params = {"place_id": place_id_to_use, "fields": details_fields, "key": api_key}
    
    try:
        details_response = requests.get(details_url, params=details_params, timeout=10)
        details_response.raise_for_status()
        details_data = details_response.json()
        print(f"DEBUG [enrich_with_google_places]: Google Place Details raw response: {str(details_data)[:300]}")
        if details_data.get("status") == "OK":
            result = details_data.get("result", {})
            photo_url = None
            if result.get("photos") and len(result["photos"]) > 0:
                photo_ref = result["photos"][0].get("photo_reference")
                if photo_ref:
                    photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={photo_ref}&key={api_key}"
            
            processed_details = {
                "google_place_id": result.get("place_id"), "name_google": result.get("name"),
                "address_google": result.get("formatted_address", result.get("vicinity")),
                "phone_number_google": result.get("international_phone_number"),
                "website_google": result.get("website"), "rating_google": result.get("rating"),
                "user_ratings_total_google": result.get("user_ratings_total"),
                "opening_hours_google": result.get("opening_hours", {}).get("weekday_text"),
                "photo_url_google": photo_url, "google_maps_url": result.get("url"),
                "business_status_google": result.get("business_status"),
                "types_google": result.get("types", []),
                "price_level_google": result.get("price_level"),
                "utc_offset_google": result.get("utc_offset")
            }
            if cache: 
                cache.set(details_cache_key, processed_details, timeout=PLACE_DETAILS_CACHE_TIMEOUT)
                print(f"DEBUG [enrich_with_google_places]: Fetched and cached Place Details for ID: {place_id_to_use}")
            return processed_details
        else:
            print(f"WARNING [enrich_with_google_places]: Google Place Details status not OK: {details_data.get('status')} for ID {place_id_to_use}. Error: {details_data.get('error_message')}")
            if cache: # Optionally cache "not found" or error for a short time
                 cache.set(details_cache_key, {"error": "API_ERROR", "status": details_data.get('status')}, timeout=300) # Cache error for 5 min
            return None 
    except Exception as e: # Catching a broader range of request/parsing errors
        print(f"ERROR [enrich_with_google_places]: Google Place Details API call/processing error for ID {place_id_to_use}: {e}")
    return None