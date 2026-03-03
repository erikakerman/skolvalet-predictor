# admission_predictor.py

import os
from schools_data import SCHOOLS, NO_FORSKOLEKLASS
from distance_checker import get_distances_from_home

# ─────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────

NEAR_HOME_LIMIT_KM = 2.0


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')


def ask_yes_no(question):
    while True:
        answer = input(f"{question} (ja/nej): ").strip().lower()
        if answer in ["ja", "nej"]:
            return answer == "ja"
        print("  Skriv 'ja' eller 'nej'.")


def ask_int(question):
    while True:
        answer = input(f"{question}: ").strip()
        if answer == "":
            return None
        try:
            return int(answer)
        except ValueError:
            print("  Ange ett år, t.ex. 2021.")


# ─────────────────────────────────────────
# PRIORITY LOGIC
# ─────────────────────────────────────────

def is_near_home(distance_km):
    return distance_km <= NEAR_HOME_LIMIT_KM


def get_priority_kommunal(distance_km, has_sibling, active_choice,
                           protected_identity=False, is_sole_nearby=False):
    """
    Returns the priority group number based on Lunds kommuns rules.
    Groups 1-5 from the Riktlinjer document.
    """
    if protected_identity:
        group = 1
    elif is_sole_nearby:
        group = 2
    elif has_sibling:
        group = 3
    elif is_near_home(distance_km):
        group = 4
    else:
        group = 5

    active_label = "aktivt val" if active_choice else "passivt val"
    return group, active_label


def get_priority_montessori(has_sibling, has_montessori, queue_year, school_key):
    if has_sibling:
        group = 1
    elif has_montessori:
        group = 2
    else:
        group = 4

    return group, queue_year


# ─────────────────────────────────────────
# CHANCE INDICATOR
# ─────────────────────────────────────────

def get_chance(group, demand, school_type):
    if school_type == "kommunal":
        if group == 3:
            return "🟢 God chans — syskonförtur är starkt"
        elif group == 4:
            if demand == "low":
                return "🟢 God chans — nära hemmet och låg efterfrågan"
            elif demand == "medium":
                return "🟡 Måttlig chans — nära hemmet men skolan är populär"
            else:
                return "🟠 Osäkert — nära hemmet men skolan är mycket efterfrågad"
        else:
            if demand == "low":
                return "🟡 Måttlig chans — inte nära hemmet men skolan har kapacitet"
            elif demand == "medium":
                return "🔴 Låg chans — inte nära hemmet och skolan är eftertraktad"
            else:
                return "🔴 Låg chans — inte nära hemmet och skolan är mycket eftertraktad"
    else:
        if group == 1:
            return "🟢 God chans — syskonförtur är starkt"
        elif group == 2:
            return "🟡 Måttlig chans — Montessoribakgrund hjälper men ködatum avgör"
        else:
            return "🔴 Låg chans — endast ködatum, hög efterfrågan"


# ─────────────────────────────────────────
# INPUT
# ─────────────────────────────────────────

def find_nearest_schools(home_address, n=6):
    print("\n  Beräknar avstånd till alla skolor...")
    all_distances = get_distances_from_home(home_address, SCHOOLS)

    if all_distances is None:
        return None, None

    sorted_schools = sorted(
        [(key, dist) for key, dist in all_distances.items() if dist is not None],
        key=lambda x: x[1]
    )

    return sorted_schools[:n], all_distances


def pick_schools_by_distance(sorted_schools):
    print("\n  Närmaste skolor från din adress:")
    print(f"  {'Nr':<4} {'Namn':<40} {'Avstånd':<10} {'Typ'}")
    print("  " + "-"*70)

    for i, (key, dist) in enumerate(sorted_schools, start=1):
        school = SCHOOLS[key]
        near = "✅" if dist <= NEAR_HOME_LIMIT_KM else "  "
        typ = "Montessori" if school["type"] == "montessori" else "Kommunal"
        print(f"  {i:<4} {near} {school['name']:<38} {dist} km   {typ}")

    print("\n  ✅ = inom 2 km (nära hemmet)")
    print("\nVälj upp till 3 skolor genom att ange deras nummer.")
    print("Exempel: 1, 3, 5")

    while True:
        raw = input("\nDina val: ").strip()
        choices = [s.strip() for s in raw.split(",")]

        selected_keys = []
        valid = True

        for c in choices:
            if not c.isdigit():
                print(f"  Ange siffror, t.ex. 1, 2, 3.")
                valid = False
                break
            idx = int(c) - 1
            if idx < 0 or idx >= len(sorted_schools):
                print(f"  Ogiltigt val: {c}. Välj mellan 1 och {len(sorted_schools)}.")
                valid = False
                break
            selected_keys.append(sorted_schools[idx][0])

        if valid and selected_keys:
            return selected_keys[:3]


def get_child_info(home_address, school_keys, all_distances):
    print("\n--- Barnets information ---\n")

    print("  Valda skolor:")
    for key in school_keys:
        dist = all_distances[key]
        near = "✅ nära hemmet" if dist <= NEAR_HOME_LIMIT_KM else "❌ inte nära hemmet"
        print(f"    {SCHOOLS[key]['name']:<40} {dist} km  {near}")

    has_sibling    = ask_yes_no("\nHar barnet syskon på någon av dessa skolor i åk F-3?")
    active_choice  = ask_yes_no("Gör du ett aktivt skolval?")
    has_montessori = ask_yes_no("Har barnet gått på en Montessoriförskola?")
    queue_year     = ask_int("Vilket år ställde du barnet i kö till Montessoriskola? (Enter för att hoppa över)")

    return {
        "distances": all_distances,
        "has_sibling": has_sibling,
        "active_choice": active_choice,
        "has_montessori": has_montessori,
        "queue_year": queue_year,
    }


# ─────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────

def print_comparison(school_keys, child):
    clear_console()
    print("\n" + "="*55)
    print("  RESULTAT — Jämförelse förskoleklass")
    print("="*55)

    recommendations = []

    for key in school_keys:
        school = SCHOOLS[key]
        name = school["name"]
        demand = school["demand"]
        school_type = school["type"]
        distance = child["distances"].get(key)

        if distance is None:
            print(f"\n  ⚠️  Hoppar över {name} — avstånd ej tillgängligt.")
            continue

        if school_type == "kommunal":
            group, label = get_priority_kommunal(
                distance,
                child["has_sibling"],
                child["active_choice"]
            )
            group_display = f"Grupp {group} – {label}"
            chance = get_chance(group, demand, school_type)
            recommendations.append((chance, name, group))

        else:
            if child["queue_year"] is None:
                print(f"\n  {name}")
                print(f"  ⚠️  Inget ködatum angivet — hoppar över Montessoriskola.")
                continue

            group, queue_year = get_priority_montessori(
                child["has_sibling"],
                child["has_montessori"],
                child["queue_year"],
                key
            )
            group_display = f"Grupp {group} – ködatum: {queue_year}"
            chance = get_chance(group, demand, school_type)
            recommendations.append((chance, name, group))

        print(f"\n  📍 {name}")
        print(f"     Avstånd    : {distance} km")
        print(f"     Typ        : {'Kommunal' if school_type == 'kommunal' else 'Fristående'}")
        print(f"     Prioritet  : {group_display}")
        print(f"     Efterfrågan: {'Hög' if demand == 'high' else 'Medel' if demand == 'medium' else 'Låg'}")
        print(f"     Chans      : {chance}")

    print("\n" + "-"*55)
    print("  💡 Rekommendation")
    print("-"*55)

    if recommendations:
        recommendations.sort(key=lambda x: x[2])
        best = recommendations[0]
        print(f"  Ditt starkaste alternativ är: {best[1]}")
        print(f"  Anledning: lägst prioritetsgrupp bland dina val.")
    else:
        print("  Inga rekommendationer tillgängliga.")

    print("="*55)


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    clear_console()
    print("=== Lunds kommun – Förskoleklass Skolvals-prediktor ===")

    while True:
        print("\n--- Din hemadress ---\n")

        while True:
            home_address = input("Din hemadress (t.ex. Stortorget 1, Lund): ").strip()
            if home_address:
                break
            print("  Ange en adress.")

        sorted_schools, all_distances = find_nearest_schools(home_address)
        if sorted_schools is None:
            continue

        school_keys = pick_schools_by_distance(sorted_schools)
        child = get_child_info(home_address, school_keys, all_distances)
        print_comparison(school_keys, child)

        again = ask_yes_no("\nVill du göra en ny jämförelse?")
        if not again:
            clear_console()
            print("Tack för att du använde Skolvals-prediktorn. Lycka till! 🍀")
            break


if __name__ == "__main__":
    main()
