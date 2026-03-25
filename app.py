# app.py

import json
from flask import Flask, render_template, request
from distance_checker import get_distances_from_home
from admission_predictor import (
    is_near_home,
    get_priority_kommunal,
    get_priority_montessori,
    get_chance,
    NEAR_HOME_LIMIT_KM,
)

app = Flask(__name__)

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE_DIR, "schools_all.json"), encoding="utf-8") as f:
    ALL_SCHOOLS = json.load(f)

KOMMUNER = sorted(set(s["kommun"] for s in ALL_SCHOOLS.values()))

RIKSSNITT = {
    "godkant_ak9":    71.9,
    "godkant_ak6":    77.4,
    "behorighet":     84.1,
    "elever_larare":  12.0,
    "antal_elever":   None,
    "legitimerade":   72.6,
    "trygghet":        8.0,
    "np_svenska_ak3": 88.0,
    "np_svenska_ak6": 76.0,
    "np_svenska_ak9": 67.0,
    "np_matte_ak3":   80.0,
    "np_matte_ak6":   62.0,
    "np_matte_ak9":   57.0,
    "studiero":        6.5,
}

STATS_LABELS = {
    "godkant_ak9":    ("Godkänt alla ämnen åk 9", "%"),
    "godkant_ak6":    ("Godkänt alla ämnen åk 6", "%"),  # fallback if no ak9
    "behorighet":     ("Behörighet gymnasiet", "%"),
    "elever_larare":  ("Elever per lärare", ""),
    "antal_elever":   ("Antal elever", ""),
    "legitimerade":   ("Legitimerade lärare", "%"),
    "trygghet":       ("Trygghet åk 5", "/10"),
    "np_svenska_ak3": ("NP svenska åk 3", "%"),
    "np_svenska_ak6": ("NP svenska åk 6", "%"),
    "np_svenska_ak9": ("NP svenska åk 9", "%"),
    "np_matte_ak3":   ("NP matematik åk 3", "%"),
    "np_matte_ak6":   ("NP matematik åk 6", "%"),
    "np_matte_ak9":   ("NP matematik åk 9", "%"),
    "studiero":       ("Studiero åk 5", "/10"),
}


def get_schools_for_kommun(kommun):
    return {k: s for k, s in ALL_SCHOOLS.items() if s["kommun"] == kommun}


def find_kommun_from_distances(distances):
    """Find which kommun the home address belongs to based on closest school."""
    if not distances:
        return None
    closest_key = min(distances, key=lambda k: distances[k] if distances[k] is not None else 99999)
    return ALL_SCHOOLS[closest_key]["kommun"]


def count_nearby_schools(home_distances, schools):
    return sum(
        1 for key, dist in home_distances.items()
        if key in schools and dist is not None and dist <= NEAR_HOME_LIMIT_KM
    )


def _color(chance):
    if "🟢" in chance: return "green"
    if "🟡" in chance: return "yellow"
    if "🟠" in chance: return "orange"
    return "red"


def format_stats(school):
    raw = school.get("stats", {})
    if not raw:
        return None
    rows = []
    for key, (label, unit) in STATS_LABELS.items():
        val = raw.get(key)
        if val is None:
            continue
        riksval = RIKSSNITT[key]
        if riksval is None:
            # No comparison (e.g. antal_elever)
            rows.append({"label": label, "value": val, "unit": unit,
                         "diff_str": "", "better": None, "neutral": True})
            continue
        diff = round(val - riksval, 1)
        if key == "elever_larare":
            better = diff < 0
            diff_str = f"{abs(diff)} färre än rikssnitt" if diff < 0 else f"{abs(diff)} fler än rikssnitt" if diff > 0 else "samma som rikssnitt"
        else:
            better = diff > 0
            diff_str = f"+{diff}{unit} vs rikssnitt" if diff > 0 else f"{diff}{unit} vs rikssnitt" if diff < 0 else "samma som rikssnitt"
        rows.append({
            "label":   label,
            "value":   val,
            "unit":    unit,
            "diff_str": diff_str,
            "better":  better,
            "neutral": diff == 0,
        })
    return rows if rows else None


KOMMUNAL_PRIORITIES = [
    {"num": 1, "title": "Skyddade personuppgifter", "desc": "Elever med skyddad identitet går alltid först."},
    {"num": 2, "title": "Enda skolan nära hemmet",  "desc": "Den enda kommunala skolan inom 2 km från hemmet."},
    {"num": 3, "title": "Syskonförtur",             "desc": "Barnet har ett syskon i åk F–3 på samma skola."},
    {"num": 4, "title": "Nära hemmet",              "desc": "Skolan ligger inom 2 km från folkbokföringsadressen."},
    {"num": 5, "title": "Övriga sökande",           "desc": "Skolan är inte barnets närmaste alternativ."},
]

PRIVAT_PRIORITIES = [
    {"num": 1, "title": "Syskonförtur",       "desc": "Barnet har ett syskon i åk F–3 på samma skola."},
    {"num": 2, "title": "Montessoribakgrund", "desc": "Barnet har gått på en Montessoriförskola."},
    {"num": 3, "title": "Övriga sökande",     "desc": "Ingen syskonförtur eller Montessoribakgrund."},
]


def build_results(school_keys, child, schools):
    kommunal_results  = []
    montessori_results = []
    nearby_count = count_nearby_schools(child["distances"], schools)

    for key in school_keys:
        school   = schools[key]
        distance = child["distances"].get(key)
        if distance is None:
            continue

        school_type = school["type"]
        stats = format_stats(school)

        if school_type == "kommunal":
            is_sole_nearby = (is_near_home(distance) and nearby_count == 1)
            group, label = get_priority_kommunal(
                distance,
                child["has_sibling"],
                child["active_choice"],
                protected_identity=child["protected_identity"],
                is_sole_nearby=is_sole_nearby,
            )
            chance = get_chance(group, "medium", school_type)
            kommunal_results.append({
                "name":         school["name"],
                "distance":     round(distance, 2),
                "near_home":    is_near_home(distance),
                "group":        group,
                "active_label": label,
                "chance":       chance,
                "color":        _color(chance),
                "priorities":   KOMMUNAL_PRIORITIES,
                "stats":        stats,
                "sort_key":     group,
            })
        else:
            if not child["queue_year"]:
                continue
            group, queue_year = get_priority_montessori(
                child["has_sibling_privat"],
                child["has_montessori"],
                child["queue_year"],
                key,
            )
            chance = get_chance(group, "medium", school_type)
            montessori_results.append({
                "name":       school["name"],
                "distance":   round(distance, 2),
                "near_home":  is_near_home(distance),
                "group":      group,
                "queue_year": queue_year,
                "chance":     chance,
                "color":      _color(chance),
                "priorities": PRIVAT_PRIORITIES,
                "stats":      stats,
                "sort_key":   (group, queue_year),
                "tied":       False,
            })

    kommunal_results.sort(key=lambda x: x["sort_key"])
    montessori_results.sort(key=lambda x: x["sort_key"])

    for i, r in enumerate(montessori_results):
        r["tied"] = any(
            j != i and montessori_results[j]["sort_key"] == r["sort_key"]
            for j in range(len(montessori_results))
        )

    return kommunal_results, montessori_results


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/skolor", methods=["POST"])
def skolor():
    """Geocode address, detect kommun, show school list with distances."""
    address = request.form.get("address", "").strip()

    if not address:
        return render_template("index.html", error="Ange din hemadress.")

    # Geocode and calculate distances to all schools
    all_distances = get_distances_from_home(address, ALL_SCHOOLS)
    if all_distances is None:
        return render_template("index.html",
                               error="Kunde inte hitta adressen. Kontrollera stavningen och försök igen.",
                               address=address)

    # Detect kommun from closest school
    kommun = find_kommun_from_distances(all_distances)
    if not kommun:
        return render_template("index.html", error="Kunde inte bestämma kommun. Försök igen.", address=address)

    # Filter to schools in that kommun with their distances
    schools = get_schools_for_kommun(kommun)
    distances = {k: round(all_distances[k], 2) for k in schools if all_distances.get(k) is not None}

    return render_template("schools.html",
                           address=address,
                           kommun=kommun,
                           schools=schools,
                           distances=distances)


@app.route("/results", methods=["POST"])
def results():
    address              = request.form.get("address", "").strip()
    kommun               = request.form.get("kommun", "").strip()
    active_choice        = request.form.get("active_choice") == "yes"
    has_montessori       = request.form.get("has_montessori") == "yes"
    has_sibling_kommunal = request.form.get("has_sibling") == "yes"
    has_sibling_privat   = request.form.get("has_sibling_privat") == "yes"
    protected_identity   = request.form.get("protected_identity") == "yes"
    queue_year_raw       = request.form.get("queue_year", "").strip()
    queue_year           = int(queue_year_raw) if queue_year_raw.isdigit() else None
    selected_keys        = request.form.getlist("schools")

    schools = get_schools_for_kommun(kommun)

    if not selected_keys:
        all_distances = get_distances_from_home(address, schools)
        distances = {k: round(all_distances[k], 2) for k in schools if all_distances and all_distances.get(k) is not None}
        return render_template("schools.html",
                               error="Välj minst en skola.",
                               address=address, kommun=kommun,
                               schools=schools, distances=distances)

    all_distances = get_distances_from_home(address, schools)
    if all_distances is None:
        return render_template("index.html",
                               error="Kunde inte hitta adressen. Försök igen.",
                               address=address)

    child = {
        "distances":          all_distances,
        "has_sibling":        has_sibling_kommunal,
        "has_sibling_privat": has_sibling_privat,
        "active_choice":      active_choice,
        "has_montessori":     has_montessori,
        "protected_identity": protected_identity,
        "queue_year":         queue_year,
    }

    kommunal_results, montessori_results = build_results(selected_keys, child, schools)

    return render_template(
        "results.html",
        kommunal_results=kommunal_results,
        montessori_results=montessori_results,
        address=address,
        kommun=kommun,
    )


if __name__ == "__main__":
    app.run(debug=True)
