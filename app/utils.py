# app/utils.py
import requests
from flask import current_app
import time

def get_coordinates_for_city(city_name):
    """Geocodes a city name to latitude, longitude, and bounding box using Nominatim."""
    nominatim_url = current_app.config.get('NOMINATIM_API_URL')
    if not nominatim_url:
        print("ERROR [get_coordinates_for_city]: Nominatim API URL not configured.")
        # current_app.logger.error("Nominatim API URL not configured.") # Use logger in prod
        return None

    headers = {'User-Agent': 'LeadForge App/0.1 (your_email@example.com)'} # IMPORTANT: Update User-Agent
    params = {'q': city_name, 'format': 'json', 'limit': 1, 'addressdetails': 1}
    
    print(f"DEBUG [get_coordinates_for_city]: Requesting Nominatim: {nominatim_url} with params: {params}")
    try:
        response = requests.get(nominatim_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"DEBUG [get_coordinates_for_city]: Nominatim raw response data: {str(data)[:500]}") # Print snippet
        if data and len(data) > 0:
            location_data = data[0]
            bbox_nominatim = location_data.get('boundingbox')
            if bbox_nominatim and len(bbox_nominatim) == 4:
                # Nominatim: [lat_min (south), lat_max (north), lon_min (west), lon_max (east)]
                # Overpass expects bbox string: "south,west,north,east"
                # So, it's: bbox_nominatim[0], bbox_nominatim[2], bbox_nominatim[1], bbox_nominatim[3]
                bbox_overpass_coords_only = f"{bbox_nominatim[0]},{bbox_nominatim[2]},{bbox_nominatim[1]},{bbox_nominatim[3]}"
                print(f"DEBUG [get_coordinates_for_city]: Calculated Overpass bbox string: {bbox_overpass_coords_only}")
                return {
                    'latitude': float(location_data.get('lat')),
                    'longitude': float(location_data.get('lon')),
                    'bounding_box_str': bbox_overpass_coords_only, # For Overpass query
                    'display_name': location_data.get('display_name')
                }
            else:
                print(f"WARNING [get_coordinates_for_city]: Bounding box not found or incomplete for {city_name} in Nominatim response: {bbox_nominatim}")
                return None
        else:
            print(f"WARNING [get_coordinates_for_city]: No data returned from Nominatim for {city_name}")
            
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR [get_coordinates_for_city]: Nominatim API HTTP error for {city_name}: {http_err} - Response: {response.text if 'response' in locals() else 'N/A'}")
    except requests.exceptions.RequestException as e:
        print(f"ERROR [get_coordinates_for_city]: Nominatim API request error for {city_name}: {e}")
    except Exception as e:
        print(f"ERROR [get_coordinates_for_city]: Error processing Nominatim response for {city_name}: {e}")
    
    # time.sleep(1.1) # Adhere to Nominatim's 1 req/sec policy - do this in the calling route if making multiple calls
    return None


def fetch_osm_data(osm_tag_key, osm_tag_value, bounding_box_str, limit=20, osm_object_types=("node", "way", "relation")):
    """
    Fetches data from Overpass API based on a key, value, and bounding box string.
    bounding_box_str should be "south_lat,west_lon,north_lat,east_lon"
    """
    overpass_url = current_app.config.get('OVERPASS_API_URL')
    if not overpass_url:
        print("ERROR [fetch_osm_data]: Overpass API URL not configured.")
        return [] # Return empty list on config error

    query_parts = []
    for obj_type in osm_object_types:
        # Correctly quote key and value for Overpass QL
        query_parts.append(f'{obj_type}["{osm_tag_key}"="{osm_tag_value}"]({bounding_box_str});')
    
    # Ensure timeout is an integer for f-string if not hardcoded
    timeout_seconds = 30
    overpass_query = f"""
    [out:json][timeout:{timeout_seconds}];
    (
      {''.join(query_parts)}
    );
    out center {limit}; 
    """
    # Note: "out center" gives a single point; "out body;" gives more data but can be larger.
    # "out geom;" gives full geometry. Choose based on needs.
    # Using "out center {limit};" is efficient for lists.

    print(f"DEBUG [fetch_osm_data]: Constructed Overpass Query:\n{overpass_query}")
    print(f"DEBUG [fetch_osm_data]: Posting to Overpass URL: {overpass_url}")
    try:
        # Overpass API expects the query in the 'data' field of a form POST
        response = requests.post(overpass_url, data={'data': overpass_query}, headers={'User-Agent': 'LeadForge App/0.1'}, timeout=timeout_seconds + 5)
        response.raise_for_status()
        data = response.json()
        print(f"DEBUG [fetch_osm_data]: Raw Overpass JSON response (first 500 chars): {str(data)[:500]}")
        elements = data.get('elements', [])
        print(f"DEBUG [fetch_osm_data]: Overpass response elements count: {len(elements)}")
        return elements
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR [fetch_osm_data]: Overpass API HTTP error: {http_err} - Status: {response.status_code} - Response: {response.text}")
    except requests.exceptions.Timeout:
        print(f"ERROR [fetch_osm_data]: Overpass API request timed out after {timeout_seconds + 5} seconds.")
    except requests.exceptions.RequestException as e:
        print(f"ERROR [fetch_osm_data]: Overpass API request error: {e}")
    except Exception as e:
        print(f"ERROR [fetch_osm_data]: Error processing Overpass response: {e}")
    return [] # Return empty list on error


def enrich_with_google_places(business_name, address=None, latitude=None, longitude=None):
    """
    Attempts to find a single place on Google and get its details.
    Uses "Find Place from Text" API and then "Place Details".
    """
    api_key = current_app.config.get('GOOGLE_PLACES_API_KEY')
    if not api_key:
        print("WARNING [enrich_with_google_places]: Google Places API key not configured for enrichment.")
        return None

    find_place_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    input_query = business_name
    if address: # OSM often has street name but not full address, this helps
        input_query += f", {address}" 
    
    find_params = {
        "input": input_query,
        "inputtype": "textquery",
        "fields": "place_id,name",
        "key": api_key
    }
    if latitude and longitude:
        find_params["locationbias"] = f"circle:2000@{latitude},{longitude}"

    place_id = None
    print(f"DEBUG [enrich_with_google_places]: Google Find Place query: '{input_query}' with params: {find_params}")
    try:
        find_response = requests.get(find_place_url, params=find_params, timeout=10)
        find_response.raise_for_status()
        find_data = find_response.json()
        print(f"DEBUG [enrich_with_google_places]: Google Find Place raw response: {str(find_data)[:300]}")
        if find_data.get("status") == "OK" and find_data.get("candidates"):
            place_id = find_data["candidates"][0].get("place_id")
            print(f"DEBUG [enrich_with_google_places]: Found Google Place ID: {place_id} for {business_name}")
        elif find_data.get("status") != "OK":
            print(f"WARNING [enrich_with_google_places]: Google Find Place status not OK: {find_data.get('status')} for {business_name}. Error: {find_data.get('error_message')}")
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR [enrich_with_google_places]: Google Find Place API HTTP error for '{business_name}': {http_err} - Response: {find_response.text if 'find_response' in locals() else 'N/A'}")
        return None
    except Exception as e:
        print(f"ERROR [enrich_with_google_places]: Google Find Place API error for '{business_name}': {e}")
        return None

    if not place_id:
        print(f"DEBUG [enrich_with_google_places]: No Google Place ID found for {business_name}.")
        return None

    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
    # Request more fields that are useful
    details_fields = "place_id,name,formatted_address,international_phone_number,website,opening_hours,price_level,rating,user_ratings_total,photo,url,business_status,type,vicinity,utc_offset_minutes"
    details_params = {
        "place_id": place_id,
        "fields": details_fields,
        "key": api_key
    }
    print(f"DEBUG [enrich_with_google_places]: Google Place Details request for ID: {place_id}")
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
                photo_width = result["photos"][0].get("width", 800) # Get original width
                if photo_ref:
                    photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={photo_width}&photoreference={photo_ref}&key={api_key}"
            
            return {
                "google_place_id": result.get("place_id"),
                "name_google": result.get("name"),
                "address_google": result.get("formatted_address", result.get("vicinity")),
                "phone_number_google": result.get("international_phone_number"), # usually better
                "website_google": result.get("website"),
                "rating_google": result.get("rating"),
                "user_ratings_total_google": result.get("user_ratings_total"),
                "opening_hours_google": result.get("opening_hours", {}).get("weekday_text"),
                "photo_url_google": photo_url,
                "google_maps_url": result.get("url"),
                "business_status_google": result.get("business_status"),
                "types_google": result.get("types", []),
                "price_level_google": result.get("price_level")
            }
        elif details_data.get("status") != "OK":
             print(f"WARNING [enrich_with_google_places]: Google Place Details status not OK: {details_data.get('status')} for ID {place_id}. Error: {details_data.get('error_message')}")
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR [enrich_with_google_places]: Google Place Details API HTTP error for ID {place_id}: {http_err} - Response: {details_response.text if 'details_response' in locals() else 'N/A'}")
    except Exception as e:
        print(f"ERROR [enrich_with_google_places]: Google Place Details API error for ID {place_id}: {e}")
    return None