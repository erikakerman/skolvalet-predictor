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

# ── Load all schools ───────────────────────────────────────────────────────────
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE_DIR, "schools_all.json"), encoding="utf-8") as f:
    ALL_SCHOOLS = json.load(f)

KOMMUNER = sorted(set(s["kommun"] for s in ALL_SCHOOLS.values()))


def get_schools_for_kommun(kommun):
    return {k: s for k, s in ALL_SCHOOLS.items() if s["kommun"] == kommun}


def count_nearby_schools(home_distances, schools):
    """Return how many schools in the kommun are within 2 km."""
    return sum(
        1 for key, dist in home_distances.items()
        if key in schools and dist is not None and dist <= NEAR_HOME_LIMIT_KM
    )


def _color(chance):
    if "🟢" in chance: return "green"
    if "🟡" in chance: return "yellow"
    if "🟠" in chance: return "orange"
    return "red"


# Priority definitions for display in results
KOMMUNAL_PRIORITIES = [
    {
        "num": 1,
        "title": "Skyddade personuppgifter",
        "desc": "Elever med skyddad identitet går alltid först.",
    },
    {
        "num": 2,
        "title": "Enda skolan nära hemmet",
        "desc": "Den enda kommunala skolan inom 2 km från hemmet.",
    },
    {
        "num": 3,
        "title": "Syskonförtur",
        "desc": "Barnet har ett syskon i åk F–3 på samma skola.",
    },
    {
        "num": 4,
        "title": "Nära hemmet",
        "desc": "Skolan ligger inom 2 km från folkbokföringsadressen.",
    },
    {
        "num": 5,
        "title": "Övriga sökande",
        "desc": "Skolan är inte barnets närmaste alternativ.",
    },
]

PRIVAT_PRIORITIES = [
    {
        "num": 1,
        "title": "Syskonförtur",
        "desc": "Barnet har ett syskon i åk F–3 på samma skola.",
    },
    {
        "num": 2,
        "title": "Montessoribakgrund",
        "desc": "Barnet har gått på en Montessoriförskola.",
    },
    {
        "num": 3,
        "title": "Övriga sökande",
        "desc": "Ingen syskonförtur eller Montessoribakgrund.",
    },
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

        if school_type == "kommunal":
            # Group 2: this school is the ONLY one within 2 km
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
                "name":       school["name"],
                "distance":   round(distance, 2),
                "near_home":  is_near_home(distance),
                "group":      group,
                "active_label": label,
                "chance":     chance,
                "color":      _color(chance),
                "priorities": KOMMUNAL_PRIORITIES,
                "sort_key":   group,
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
    return render_template("index.html", kommuner=KOMMUNER)


@app.route("/schools", methods=["GET"])
def schools_for_kommun():
    kommun = request.args.get("kommun", "")
    if not kommun:
        return ""
    schools = get_schools_for_kommun(kommun)
    return render_template("_school_list.html", schools=schools)


@app.route("/results", methods=["POST"])
def results():
    kommun               = request.form.get("kommun", "").strip()
    home_address         = request.form.get("address", "").strip()
    active_choice        = request.form.get("active_choice") == "yes"
    has_montessori       = request.form.get("has_montessori") == "yes"
    has_sibling_kommunal = request.form.get("has_sibling") == "yes"
    has_sibling_privat   = request.form.get("has_sibling_privat") == "yes"
    protected_identity   = request.form.get("protected_identity") == "yes"
    queue_year_raw       = request.form.get("queue_year", "").strip()
    queue_year           = int(queue_year_raw) if queue_year_raw.isdigit() else None
    selected_keys        = request.form.getlist("schools")

    schools = get_schools_for_kommun(kommun)

    has_kommunal = any(schools.get(k, {}).get("type") == "kommunal" for k in selected_keys)

    if not selected_keys:
        return render_template("index.html", kommuner=KOMMUNER,
                               error="Välj minst en skola.", selected_kommun=kommun)

    if has_kommunal and not home_address:
        return render_template("index.html", kommuner=KOMMUNER,
                               error="Fyll i din hemadress.", selected_kommun=kommun)

    if home_address:
        all_distances = get_distances_from_home(home_address, schools)
        if all_distances is None:
            return render_template("index.html", kommuner=KOMMUNER,
                                   error="Kunde inte hitta adressen. Försök igen.",
                                   selected_kommun=kommun)
    else:
        all_distances = {key: 0 for key in schools}

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
        address=home_address,
        kommun=kommun,
    )


if __name__ == "__main__":
    app.run(debug=True)
