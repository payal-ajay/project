import json
import math
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

IATA_COORDS = {
    "LHR": (51.477, -0.461), "LGW": (51.148, -0.190), "MAN": (53.353, -2.275),
    "JFK": (40.640, -73.779), "EWR": (40.692, -74.174), "LAX": (33.943, -118.408),
    "ORD": (41.974, -87.907), "SFO": (37.619, -122.375), "CDG": (49.013, 2.550),
    "AMS": (52.310, 4.768),  "FRA": (50.033, 8.571),  "DXB": (25.253, 55.364),
    "SIN": (1.359, 103.989), "BOM": (19.089, 72.868),  "DEL": (28.556, 77.100),
    "BLR": (13.198, 77.706), "HKG": (22.310, 113.915), "NRT": (35.765, 140.386),
    "SYD": (-33.947, 151.179), "DFW": (32.897, -97.038), "ATL": (33.640, -84.427),
    "BOS": (42.366, -71.009), "MIA": (25.796, -80.287), "SEA": (47.450, -122.309),
    "YYZ": (43.677, -79.630), "GRU": (-23.432, -46.469), "MEX": (19.436, -99.072),
}

FLIGHT_FACTORS = {
    "ECONOMY": 0.255, "PREMIUM_ECONOMY": 0.381,
    "BUSINESS": 0.573, "FIRST": 1.020,
}

HOTEL_FACTOR_PER_NIGHT = 20.8

GROUND_FACTORS = {
    "TAXI": 0.149, "RENTAL_CAR": 0.171,
    "RAIL": 0.041, "BUS": 0.089, "UNKNOWN": 0.149,
}

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def get_flight_distance(origin, destination):
    o = IATA_COORDS.get(origin.upper())
    d = IATA_COORDS.get(destination.upper())
    if not o or not d:
        return None
    return round(haversine_km(o[0], o[1], d[0], d[1]), 1)

def parse_travel_json(file_path):
    errors = []
    records = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [], [f"Could not read JSON: {str(e)}"]

    trips = data if isinstance(data, list) else data.get("trips", [data])
    row_idx = 0

    for trip in trips:
        traveler = trip.get("travelerName", "Unknown Traveler")
        trip_id = trip.get("tripId", "")

        for segment in trip.get("segments", []):
            seg_type = segment.get("type", "").upper()
            rec = {
                "_row_index": row_idx,
                "_raw": {**segment, "tripId": trip_id, "travelerName": traveler},
                "source_type": "TRAVEL", "scope": "SCOPE_3", "parse_errors": [],
            }

            if seg_type == "AIR":
                origin = segment.get("origin_iata", "").upper()
                dest = segment.get("destination_iata", "").upper()
                travel_class = segment.get("class_of_service", "ECONOMY").upper()
                dist = get_flight_distance(origin, dest)
                if dist is None:
                    rec["parse_errors"].append(f"Row {row_idx}: unknown IATA {origin}/{dest}")
                    dist = 0
                rec.update({
                    "activity_date": segment.get("departure_date", ""),
                    "origin_iata": origin, "destination_iata": dest,
                    "travel_class": travel_class, "transport_mode": "AIR",
                    "category": "Air Travel", "distance_km": dist,
                    "quantity": dist, "unit": "KM",
                    "quantity_co2e_kg": round(dist * FLIGHT_FACTORS.get(travel_class, 0.255), 2),
                    "emission_factor_used": f"{FLIGHT_FACTORS.get(travel_class, 0.255)} kgCO2e/km ({travel_class})",
                    "emission_factor_source": "DEFRA 2023 (with RFI multiplier)",
                    "activity_description": f"Flight {origin}→{dest} ({travel_class}) — {traveler}",
                })

            elif seg_type == "HOTEL":
                check_in = segment.get("check_in", "")
                check_out = segment.get("check_out", "")
                nights = segment.get("nights")
                if not nights and check_in and check_out:
                    try:
                        nights = (datetime.strptime(check_out, "%Y-%m-%d") - datetime.strptime(check_in, "%Y-%m-%d")).days
                    except ValueError:
                        nights = 1
                nights = nights or 1
                rec.update({
                    "activity_date": check_in, "category": "Hotel Stay",
                    "transport_mode": "HOTEL", "quantity": nights, "unit": "NIGHT",
                    "quantity_co2e_kg": round(nights * HOTEL_FACTOR_PER_NIGHT, 2),
                    "emission_factor_used": f"{HOTEL_FACTOR_PER_NIGHT} kgCO2e/night",
                    "emission_factor_source": "DEFRA 2023 Business Travel",
                    "facility_or_entity": segment.get("hotel_name", ""),
                    "activity_description": f"Hotel: {segment.get('hotel_name','Unknown')} — {nights} nights — {traveler}",
                })

            elif seg_type == "GROUND":
                mode = segment.get("mode", "UNKNOWN").upper()
                dist = segment.get("distance_km", 0)
                factor = GROUND_FACTORS.get(mode, 0.149)
                rec.update({
                    "activity_date": segment.get("date", ""),
                    "category": f"Ground Transport ({mode.title()})",
                    "transport_mode": mode, "quantity": dist, "unit": "KM",
                    "distance_km": dist,
                    "quantity_co2e_kg": round(dist * factor, 2),
                    "emission_factor_used": f"{factor} kgCO2e/km ({mode})",
                    "emission_factor_source": "DEFRA 2023",
                    "activity_description": f"Ground transport ({mode}) {dist} km — {traveler}",
                })

            errors.extend(rec["parse_errors"])
            records.append(rec)
            row_idx += 1

    return records, errors