# fetch_schools.py
#
# Run this script to build your schools database.
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

OUTPUT_FILE   = "schools_all.json"
FAILED_FILE   = "failed_schools.json"
GEOCODE_DELAY = 1.1   # seconds between geocoding calls (Nominatim rate limit)
API_DELAY     = 0.2   # seconds between Skolverket API calls (be polite)
BASE_URL      = "https://api.skolverket.se/skolenhetsregistret/v1"

# Set which regions to fetch. Each region has a 2-digit prefix.
# Run 1 (södra Sverige):  ["01", "03", "04", "05", "06", "07", "08", "09", "10"]
# Run 2 (mellersta):      ["13", "14", "17", "18", "19", "20"]
# Run 3 (norra Sverige):  ["21", "22", "23", "24", "25"]
# Skåne ("12") already done — leave it out.
FILTER_PREFIXES = ["21", "22", "23", "24", "25"]

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

if FILTER_PREFIXES:
    kommuner = [k for k in kommuner if any(k["Kommunkod"].startswith(p) for p in FILTER_PREFIXES)]
    print(f"Filtered to {len(FILTER_PREFIXES)} region(s): {len(kommuner)} kommuner")

print()

# ─── Step 2: Load existing progress ───────────────────────────────────────────

try:
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        all_schools = json.load(f)
    print(f"Resuming — {len(all_schools)} schools already saved.")
except FileNotFoundError:
    all_schools = {}

try:
    with open(FAILED_FILE, encoding="utf-8") as f:
        failed_schools = json.load(f)
    print(f"Resuming — {len(failed_schools)} failed schools already logged.")
except FileNotFoundError:
    failed_schools = []

print()
total_saved   = len(all_schools)
total_skipped = 0

# ─── Step 3: For each kommun, fetch schools ───────────────────────────────────

for i, k in enumerate(kommuner):
    kommun_kod  = k["Kommunkod"]
    kommun_namn = k["Namn"]

    print(f"[{i+1}/{len(kommuner)}] {kommun_namn} ({kommun_kod})")

    list_data = get_json(f"{BASE_URL}/skolenhet?kommunkod={kommun_kod}")
    if not list_data:
        print(f"  Could not fetch school list — skipping.")
        continue

    schools_in_kommun = [
        s for s in list_data.get("Skolenheter", [])
        if s.get("Kommunkod") == kommun_kod and s.get("Status") == "Aktiv"
    ]

    print(f"  {len(schools_in_kommun)} active schools — fetching details...")

    for school in schools_in_kommun:
        school_kod = school.get("Skolenhetskod", "")

        if school_kod in all_schools:
            continue

        detail_data = get_json(f"{BASE_URL}/skolenhet/{school_kod}")
        if not detail_data:
            total_skipped += 1
            continue

        info = detail_data.get("SkolenhetInfo", {})

        if info.get("Status") != "Aktiv":
            continue

        skolformer = info.get("Skolformer", [])
        school_form_codes = [sf.get("SkolformKod") for sf in skolformer]

        if "11" not in school_form_codes:
            continue

        has_ak1 = any(
            sf.get("SkolformKod") == "11" and sf.get("Ak1") is True
            for sf in skolformer
        )
        if not has_ak1:
            continue

        besok   = info.get("Besoksadress", {})
        address = besok.get("Adress", "")
        ort     = besok.get("Ort", kommun_namn)

        if not address:
            print(f"  No address for {info.get('Namn')} — skipping")
            failed_schools.append({
                "school_kod": school_kod,
                "name":       info.get("Namn", ""),
                "type":       "kommunal" if info.get("Huvudman", {}).get("Typ", "") == "Kommun" else "privat",
                "kommun":     kommun_namn,
                "kommunkod":  kommun_kod,
                "address":    "NO ADDRESS",
            })
            total_skipped += 1
            continue

        huvudman_typ = info.get("Huvudman", {}).get("Typ", "")
        school_type  = "kommunal" if huvudman_typ == "Kommun" else "privat"

        lat, lon = geocode(address, ort)
        if lat is None:
            print(f"  Could not geocode {info.get('Namn')} at {address}, {ort}")
            failed_schools.append({
                "school_kod": school_kod,
                "name":       info.get("Namn", ""),
                "type":       school_type,
                "kommun":     kommun_namn,
                "kommunkod":  kommun_kod,
                "address":    f"{address}, {ort}",
            })
            total_skipped += 1
            continue

        all_schools[school_kod] = {
            "name":      info.get("Namn", ""),
            "type":      school_type,
            "kommun":    kommun_namn,
            "kommunkod": kommun_kod,
            "address":   f"{address}, {ort}",
            "coords":    [lat, lon],
        }

        total_saved += 1
        print(f"  ✅ {info.get('Namn')} ({school_type}) — {lat}, {lon}")

    # Save progress after every kommun
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_schools, f, ensure_ascii=False, indent=2)
    with open(FAILED_FILE, "w", encoding="utf-8") as f:
        json.dump(failed_schools, f, ensure_ascii=False, indent=2)
    print(f"  Progress saved — {total_saved} schools total, {len(failed_schools)} failed\n")


# ─── Done ─────────────────────────────────────────────────────────────────────

print("=" * 55)
print(f"Done!")
print(f"  Schools saved:   {total_saved}")
print(f"  Schools skipped: {total_skipped}")
print(f"  Output file:     {OUTPUT_FILE}")
print(f"  Failed file:     {FAILED_FILE}")
if failed_schools:
    print(f"\n  Failed schools ({len(failed_schools)} total):")
    for s in failed_schools:
        print(f"    {s['kommun']:<20} {s['name']:<35} {s['address']}")
