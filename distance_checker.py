# distance_checker.py
# Now only geocodes the HOME address (1 request).
# School coordinates are hardcoded in schools_data.py.

import time
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

geolocator = Nominatim(user_agent="skolvalet_predictor")


def get_coordinates(address):
    """Converts a street address into (latitude, longitude)."""
    try:
        location = geolocator.geocode(address)
        if location:
            return (location.latitude, location.longitude)
        else:
            return None
    except Exception as e:
        print(f"  Could not look up address: {e}")
        return None


def calculate_distance_km(coords1, coords2):
    """Calculates straight-line distance in km between two coordinate pairs."""
    return round(geodesic(coords1, coords2).kilometers, 2)


def get_distances_from_home(home_address, schools):
    """
    Geocodes only the home address (1 request).
    Uses hardcoded coords from each school in schools_data.py.
    Returns a dict of distances in km per school key.
    """
    print(f"\n  Looking up address: {home_address}...")
    time.sleep(1)  # Brief pause to be polite to Nominatim
    home_coords = get_coordinates(home_address)

    if home_coords is None:
        print("  ❌ Could not find your address. Please check and try again.")
        return None

    print(f"  ✅ Address found!")

    distances = {}
    for key, school in schools.items():
        school_coords = school.get("coords")
        if school_coords:
            dist = calculate_distance_km(home_coords, school_coords)
            distances[key] = dist
        else:
            print(f"  ⚠️ No coords for {school['name']}")
            distances[key] = None

    return distances