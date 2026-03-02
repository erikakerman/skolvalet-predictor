# app.py

from flask import Flask, render_template, request
from schools_data import SCHOOLS
from distance_checker import get_distances_from_home
from admission_predictor import (
    is_near_home,
    get_priority_kommunal,
    get_priority_montessori,
    get_chance,
    NEAR_HOME_LIMIT_KM,
)

app = Flask(__name__)

DEMAND_SORT = {"low": 0, "medium": 1, "high": 2}

DEMAND_LABEL = {"low": "Låg", "medium": "Medel", "high": "Hög"}


def find_nearest_schools(home_address, n=None):
    all_distances = get_distances_from_home(home_address, SCHOOLS)
    if all_distances is None:
        return None, None

    sorted_schools = sorted(
        [(key, dist) for key, dist in all_distances.items() if dist is not None],
        key=lambda x: x[1]
    )

    if n:
        return sorted_schools[:n], all_distances
    return sorted_schools, all_distances


def build_results(school_keys, child):
    kommunal_results = []
    montessori_results = []

    for key in school_keys:
        school = SCHOOLS[key]
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
            chance = get_chance(group, school["demand"], school_type)
            sort_key = (group, DEMAND_SORT[school["demand"]])

            if "🟢" in chance:
                color = "green"
            elif "🟡" in chance:
                color = "yellow"
            elif "🟠" in chance:
                color = "orange"
            else:
                color = "red"

            kommunal_results.append({
                "name": school["name"],
                "area": school.get("area", ""),
                "distance": distance,
                "near_home": is_near_home(distance),
                "group": group_display,
                "demand": DEMAND_LABEL[school["demand"]],
                "chance": chance,
                "color": color,
                "sort_key": sort_key,
            })

        else:
            if not child["queue_year"]:
                continue
            group, queue_year = get_priority_montessori(
                child["has_sibling"],
                child["has_montessori"],
                child["queue_year"],
                key
            )
            group_display = f"Grupp {group} – ködatum: {queue_year}"
            chance = get_chance(group, school["demand"], school_type)
            sort_key = (group, queue_year)

            if "🟢" in chance:
                color = "green"
            elif "🟡" in chance:
                color = "yellow"
            elif "🟠" in chance:
                color = "orange"
            else:
                color = "red"

            montessori_results.append({
                "name": school["name"],
                "area": school.get("area", ""),
                "distance": distance,
                "near_home": is_near_home(distance),
                "group": group_display,
                "demand": DEMAND_LABEL[school["demand"]],
                "chance": chance,
                "color": color,
                "sort_key": sort_key,
            })

    kommunal_results.sort(key=lambda x: x["sort_key"])
    montessori_results.sort(key=lambda x: x["sort_key"])

    # Flag montessori results that are tied (same group and queue_year)
    for i, r in enumerate(montessori_results):
        tied = any(
            j != i and
            montessori_results[j]["sort_key"] == r["sort_key"]
            for j in range(len(montessori_results))
        )
        r["tied"] = tied

    return kommunal_results, montessori_results


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", schools=SCHOOLS)


@app.route("/results", methods=["POST"])
def results():
    home_address = request.form.get("address", "").strip()
    has_sibling = request.form.get("has_sibling") == "yes"
    active_choice = request.form.get("active_choice") == "yes"
    has_montessori = request.form.get("has_montessori") == "yes"
    queue_year_raw = request.form.get("queue_year", "").strip()
    queue_year = int(queue_year_raw) if queue_year_raw.isdigit() else None

    active_tab = request.form.get("active_tab", "kommunal")
    selected_keys = request.form.getlist("schools")

    # Only require address if any kommunal schools are selected
    has_kommunal = any(SCHOOLS.get(k, {}).get("type") == "kommunal" for k in selected_keys)
    address_required = has_kommunal or active_tab == "kommunal"

    if not selected_keys or (address_required and not home_address):
        return render_template(
            "index.html",
            error="Välj minst en skola." if not selected_keys else "Fyll i din hemadress.",
            schools=SCHOOLS,
            active_tab=active_tab
        )

    if home_address:
        _, all_distances = find_nearest_schools(home_address)
        if all_distances is None:
            return render_template(
                "index.html",
                error="Kunde inte hitta adressen. Försök igen.",
                schools=SCHOOLS,
                active_tab=active_tab
            )
    else:
        # No address needed — montessori only, distance not a factor
        all_distances = {key: 0 for key in SCHOOLS}

    child = {
        "distances": all_distances,
        "has_sibling": has_sibling,
        "active_choice": active_choice,
        "has_montessori": has_montessori,
        "queue_year": queue_year,
    }

    kommunal_results, montessori_results = build_results(selected_keys, child)

    return render_template(
        "results.html",
        kommunal_results=kommunal_results,
        montessori_results=montessori_results,
        address=home_address,
    )


if __name__ == "__main__":
    app.run(debug=True)
