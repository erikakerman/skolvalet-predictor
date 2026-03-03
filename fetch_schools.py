# fetch_schools.py
#
# Run this script ONCE to build your schools database.
# It fetches all active grundskolor from Skolverket's API,
# geocodes their addresses, and saves everything to schools_all.json.
#
# Usage:
#   py fetch_schools.py
#
# Requirements:
#   py -m pip install requests geopy

import json
import time
import requests
from geopy.geocoders import Nominatim

# ─── Config ───────────────────────────────────────────────────────────────────

OUTPUT_FILE    = "schools_all.json"
GEOCODE_DELAY  = 1.1   # seconds between geocoding calls (Nominatim rate limit)
API_DELAY      = 0.2   # seconds between Skolverket API calls (be polite)
BASE_URL       = "https://api.skolverket.se/skolenhetsregistret/v1"

# SKÅNE FILTER: kommun codes in Skåne all start with "12"
# To fetch ALL of Sweden later, set this to None.
FILTER_REGION_PREFIX = "12"

geolocator = Nominatim(user_agent="skolvalet-prefetch/1.0")

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_json(url):
    """Fetch a URL and return parsed JSON. Retries 3 times on failure."""
    for attempt in range(3):
        try:
            time.sleep(API_DELAY)
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"    Retry {attempt+1}/3 — {e}")
            time.sleep(2)
    return None


def geocode(address, ort):
    """Convert an address to (lat, lon). Returns (None, None) on failure."""
    query = f"{address}, {ort}, Sverige"
    try:
        time.sleep(GEOCODE_DELAY)
        result = geolocator.geocode(query)
        if result:
            return round(result.latitude, 6), round(result.longitude, 6)
    except Exception as e:
        print(f"    Geocode error: {e}")
    return None, None


# ─── Step 1: Fetch all kommuner ───────────────────────────────────────────────

print("Fetching kommuner from Skolverket...")
data = get_json(f"{BASE_URL}/kommun")
if not data:
    print("Could not reach API. Check your internet connection.")
    exit(1)

kommuner = data.get("Kommuner", [])
print(f"Total kommuner in Sweden: {len(kommuner)}")

if FILTER_REGION_PREFIX:
    kommuner = [k for k in kommuner if k["Kommunkod"].startswith(FILTER_REGION_PREFIX)]
    print(f"Filtered to prefix '{FILTER_REGION_PREFIX}': {len(kommuner)} kommuner")

print()

# ─── Step 2: For each kommun, fetch school list ───────────────────────────────

# Load existing progress if the file already exists (so we can resume)
try:
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        all_schools = json.load(f)
    print(f"Resuming — {len(all_schools)} schools already saved.\n")
except FileNotFoundError:
    all_schools = {}

total_saved   = len(all_schools)
total_skipped = 0

for i, k in enumerate(kommuner):
    kommun_kod  = k["Kommunkod"]
    kommun_namn = k["Namn"]

    print(f"[{i+1}/{len(kommuner)}] {kommun_namn} ({kommun_kod})")

    # Fetch list of all schools in this kommun
    list_data = get_json(f"{BASE_URL}/skolenhet?kommunkod={kommun_kod}")
    if not list_data:
        print(f"  Could not fetch school list — skipping.")
        continue

    # Filter to only this kommun (API returns all, we filter client-side)
    # and only active schools
    schools_in_kommun = [
        s for s in list_data.get("Skolenheter", [])
        if s.get("Kommunkod") == kommun_kod and s.get("Status") == "Aktiv"
    ]

    print(f"  {len(schools_in_kommun)} active schools — fetching details...")

    for school in schools_in_kommun:
        school_kod = school.get("Skolenhetskod", "")

        # Skip if already saved (allows resuming)
        if school_kod in all_schools:
            continue

        # Fetch full detail for this school
        detail_data = get_json(f"{BASE_URL}/skolenhet/{school_kod}")
        if not detail_data:
            total_skipped += 1
            continue

        info = detail_data.get("SkolenhetInfo", {})

        # Only keep active grundskolor
        if info.get("Status") != "Aktiv":
            continue

        skolformer = info.get("Skolformer", [])
        school_form_codes = [sf.get("SkolformKod") for sf in skolformer]

        # Must be a grundskola (kod 11)
        if "11" not in school_form_codes:
            continue

        # Must start at year 1 (Ak1 = True), which means it has förskoleklass
        # This filters out schools that only cover years 4-9 etc.
        has_ak1 = any(
            sf.get("SkolformKod") == "11" and sf.get("Ak1") is True
            for sf in skolformer
        )
        if not has_ak1:
            continue

        # Extract address
        besok = info.get("Besoksadress", {})
        address = besok.get("Adress", "")
        ort     = besok.get("Ort", kommun_namn)

        if not address:
            print(f"  No address for {info.get('Namn')} — skipping")
            total_skipped += 1
            continue

        # Determine kommunal or privat
        huvudman_typ = info.get("Huvudman", {}).get("Typ", "")
        school_type  = "kommunal" if huvudman_typ == "Kommun" else "privat"

        # Geocode
        lat, lon = geocode(address, ort)
        if lat is None:
            print(f"  Could not geocode {info.get('Namn')} at {address}, {ort}")
            total_skipped += 1
            continue

        # Save
        all_schools[school_kod] = {
            "name":       info.get("Namn", ""),
            "type":       school_type,
            "kommun":     kommun_namn,
            "kommunkod":  kommun_kod,
            "address":    f"{address}, {ort}",
            "coords":     [lat, lon],
        }

        total_saved += 1
        print(f"  ✅ {info.get('Namn')} ({school_type}) — {lat}, {lon}")

    # Save progress after every kommun
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_schools, f, ensure_ascii=False, indent=2)
    print(f"  Progress saved — {total_saved} schools total\n")


# ─── Done ─────────────────────────────────────────────────────────────────────

print("=" * 55)
print(f"Done!")
print(f"  Schools saved:   {total_saved}")
print(f"  Schools skipped: {total_skipped}")
print(f"  Output file:     {OUTPUT_FILE}")
