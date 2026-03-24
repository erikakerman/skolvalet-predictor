# merge_statistics.py
#
# Merges school statistics from Skolverket's statistikdatabas
# into schools_all.json.
#
# Usage:
#   py merge_statistics.py
#
# Input files needed in the same folder:
#   - schools_all.json         (your existing school database)
#   - Underlag_for_analys.xlsx (downloaded from Skolverket statistikdatabas)
#
# The script adds these fields to each school (where data exists):
#   godkant_ak9    - % elever med godkänt i alla ämnen åk 9
#   behorighet     - % behöriga till gymnasiets nationella program
#   elever_larare  - Antal elever per lärare
#   legitimerade   - % lärare med legitimation och behörighet
#   trygghet       - Elevers upplevelse av trygghet åk 5 (0-10)
#   studiero       - Elevers upplevelse av studiero åk 5 (0-10)

import json
import re
import os
import pandas as pd

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
SCHOOLS_FILE = os.path.join(BASE_DIR, "schools_all.json")
STATS_FILE   = os.path.join(BASE_DIR, "Underlag_for_analys.xlsx")

# ── Row indices for each metric (0-indexed) ───────────────────────────────────
METRIC_ROWS = {
    "godkant_ak9":   29,   # % godkänt alla ämnen åk 9
    "behorighet":    30,   # % behöriga till gymnasiet
    "elever_larare": 17,   # Elever per lärare
    "legitimerade":  13,   # % legitimerade lärare
    "trygghet":      31,   # Trygghet åk 5 (skolenkät)
    "studiero":      33,   # Studiero åk 5 (skolenkät)
}

def clean_value(val):
    """Convert a cell value to float or None."""
    if val is None:
        return None
    s = str(val).strip()
    # Skolverket uses '.', '..' and '...' for missing/secret data
    if s in ('.', '..', '...', '-', '', 'nan'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


print("Loading files...")
with open(SCHOOLS_FILE, encoding="utf-8") as f:
    schools = json.load(f)

print(f"  {len(schools)} schools loaded from schools_all.json")

df = pd.read_excel(STATS_FILE, header=None)
print(f"  Statistics file loaded: {df.shape[0]} rows × {df.shape[1]} columns")

# ── Build lookup: skolenhetskod → stats dict ──────────────────────────────────
print("\nExtracting statistics per skolenhet...")

stats_by_code = {}
matched_cols = 0

for col in range(df.shape[1]):
    header = str(df.iloc[2, col])
    # Skolenhet columns end with (8-digit code)
    match = re.search(r'\((\d{8})\)$', header)
    if not match:
        continue

    code = match.group(1)
    matched_cols += 1

    entry = {}
    for metric_name, row_idx in METRIC_ROWS.items():
        val = clean_value(df.iloc[row_idx, col])
        if val is not None:
            entry[metric_name] = val

    if entry:
        stats_by_code[code] = entry

print(f"  Found {matched_cols} skolenhet columns")
print(f"  {len(stats_by_code)} had at least one data point")

# ── Merge into schools_all.json ───────────────────────────────────────────────
print("\nMerging into schools_all.json...")

merged   = 0
no_match = 0

for school_code, school in schools.items():
    if school_code in stats_by_code:
        school["stats"] = stats_by_code[school_code]
        merged += 1
    else:
        no_match += 1

print(f"  Merged:    {merged} schools got statistics")
print(f"  No match:  {no_match} schools had no statistics (likely F-6 only)")

# ── Save ──────────────────────────────────────────────────────────────────────
with open(SCHOOLS_FILE, "w", encoding="utf-8") as f:
    json.dump(schools, f, ensure_ascii=False, indent=2)

print(f"\nDone! Updated {SCHOOLS_FILE}")
print("\nExample of what a school entry looks like now:")
for code, school in schools.items():
    if "stats" in school and len(school["stats"]) >= 3:
        print(f"  {school['name']} ({school['kommun']}):")
        for k, v in school["stats"].items():
            print(f"    {k}: {v}")
        break
