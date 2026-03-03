# app.py

import json
from flask import Flask, render_template, request
from distance_checker import get_distances_from_home
from admission_predictor import (
    is_near_home,
    get_priority_kommunal,
    get_priority_montessori,
    get_chance,
)

app = Flask(__name__)

# ── Load all schools from JSON ─────────────────────────────────────────────────
with open("schools_all.json", encoding="utf-8") as f:
    ALL_SCHOOLS = json.load(f)

# Build sorted list of kommuner for the dropdown
KOMMUNER = sorted(set(s["kommun"] for s in ALL_SCHOOLS.values()))

DEMAND_SORT  = {"low": 0, "medium": 1, "high": 2}
DEMAND_LABEL = {"low": "Låg", "medium": "Medel", "high": "Hög"}


def get_schools_for_kommun(kommun):
    """Return only schools belonging to the selected kommun."""
    return {
        key: school
        for key, school in ALL_SCHOOLS.items()
        if school["kommun"] == kommun
    }


def find_distances(home_address, schools):
    return get_distances_from_home(home_address, schools)


def build_results(school_keys, child, schools):
    kommunal_results  = []
    montessori_results = []

    for key in school_keys:
        school   = schools[key]
        distance = child["distances"].get(key)
        if distance is None:
            continue

        school_type = school["type"]

        if school_type == "kommunal":
            group, label = get_priority_kommunal(
                distance,
                child["has_sibling"],
                child["active_choice"]
            )
            group_display = f"Grupp {group} – {label}"
            chance    = get_chance(group, "medium", school_type)
            sort_key  = group
            color     = _color(chance)

            kommunal_results.append({
                "name":      school["name"],
                "distance":  round(distance, 2),
                "near_home": is_near_home(distance),
                "group":     group_display,
                "chance":    chance,
                "color":     color,
                "sort_key":  sort_key,
            })

        else:  # privat / montessori
            if not child["queue_year"]:
                continue
            group, queue_year = get_priority_montessori(
                child["has_sibling_privat"],
                child["has_montessori"],
                child["queue_year"],
                key
            )
            group_display = f"Grupp {group} – ködatum: {queue_year}"
            chance   = get_chance(group, "medium", school_type)
            sort_key = (group, queue_year)
            color    = _color(chance)

            montessori_results.append({
                "name":      school["name"],
                "distance":  round(distance, 2),
                "near_home": is_near_home(distance),
                "group":     group_display,
                "chance":    chance,
                "color":     color,
                "sort_key":  sort_key,
                "tied":      False,
            })

    kommunal_results.sort(key=lambda x: x["sort_key"])
    montessori_results.sort(key=lambda x: x["sort_key"])

    # Flag tied montessori results
    for i, r in enumerate(montessori_results):
        r["tied"] = any(
            j != i and montessori_results[j]["sort_key"] == r["sort_key"]
            for j in range(len(montessori_results))
        )

    return kommunal_results, montessori_results


def _color(chance):
    if "🟢" in chance: return "green"
    if "🟡" in chance: return "yellow"
    if "🟠" in chance: return "orange"
    return "red"


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", kommuner=KOMMUNER)


@app.route("/schools", methods=["GET"])
def schools_for_kommun():
    """AJAX endpoint — returns school list HTML for a selected kommun."""
    kommun = request.args.get("kommun", "")
    if not kommun:
        return ""
    schools = get_schools_for_kommun(kommun)
    return render_template("_school_list.html", schools=schools)


@app.route("/results", methods=["POST"])
def results():
    kommun       = request.form.get("kommun", "").strip()
    home_address = request.form.get("address", "").strip()
    active_choice        = request.form.get("active_choice") == "yes"
    has_montessori       = request.form.get("has_montessori") == "yes"
    has_sibling_kommunal = request.form.get("has_sibling") == "yes"
    has_sibling_privat   = request.form.get("has_sibling_privat") == "yes"
    queue_year_raw       = request.form.get("queue_year", "").strip()
    queue_year           = int(queue_year_raw) if queue_year_raw.isdigit() else None
    selected_keys        = request.form.getlist("schools")

    schools = get_schools_for_kommun(kommun)

    has_kommunal = any(schools.get(k, {}).get("type") == "kommunal" for k in selected_keys)
    has_privat   = any(schools.get(k, {}).get("type") == "privat"   for k in selected_keys)

    if not selected_keys:
        return render_template("index.html", kommuner=KOMMUNER,
                               error="Välj minst en skola.", selected_kommun=kommun)

    if has_kommunal and not home_address:
        return render_template("index.html", kommuner=KOMMUNER,
                               error="Fyll i din hemadress.", selected_kommun=kommun)

    if home_address:
        all_distances = find_distances(home_address, schools)
        if all_distances is None:
            return render_template("index.html", kommuner=KOMMUNER,
                                   error="Kunde inte hitta adressen. Försök igen.",
                                   selected_kommun=kommun)
    else:
        all_distances = {key: 0 for key in schools}

    child = {
        "distances":         all_distances,
        "has_sibling":       has_sibling_kommunal,
        "has_sibling_privat": has_sibling_privat,
        "active_choice":     active_choice,
        "has_montessori":    has_montessori,
        "queue_year":        queue_year,
    }

    kommunal_results, montessori_results = build_results(selected_keys, child, schools)

    return render_template(
        "results.html",
        kommunal_results=kommunal_results,
        montessori_results=montessori_results,
        address=home_address,
        kommun=kommun,
    )


if __name__ == "__main__":
    app.run(debug=True)
