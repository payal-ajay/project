import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

SAP_COLUMN_MAP = {
    "Buchungsdatum": "posting_date", "Belegdatum": "document_date",
    "Werk": "plant_code", "Material": "material_number",
    "Materialkurztext": "material_description", "Bewegungsart": "movement_type",
    "Menge": "quantity", "Mengeneinheit": "unit",
    "Warengruppe": "material_group", "Buchungskreis": "company_code",
    "Kostenstelle": "cost_center",
    "Posting Date": "posting_date", "Document Date": "document_date",
    "Plant": "plant_code", "Material Description": "material_description",
    "Movement Type": "movement_type", "Quantity": "quantity",
    "Unit": "unit", "Material Group": "material_group",
}

PLANT_LOOKUP = {
    "1000": "Hamburg HQ", "2000": "Munich Plant",
    "3000": "Frankfurt Warehouse", "GB01": "London Office",
    "US01": "New York Office", "IN01": "Bangalore Office",
}

MATERIAL_GROUP_MAP = {
    "FUEL01": {"category": "Natural Gas", "scope": "SCOPE_1"},
    "FUEL02": {"category": "Diesel", "scope": "SCOPE_1"},
    "FUEL03": {"category": "Petrol/Gasoline", "scope": "SCOPE_1"},
    "FUEL04": {"category": "LPG", "scope": "SCOPE_1"},
    "PROC01": {"category": "Purchased Goods", "scope": "SCOPE_3"},
    "PROC02": {"category": "Capital Goods", "scope": "SCOPE_3"},
    "UTIL01": {"category": "Electricity", "scope": "SCOPE_2"},
}

UNIT_NORMALIZATION = {
    "L": "LITER", "LTR": "LITER", "KG": "KG",
    "TO": "TONNE", "T": "TONNE", "M3": "LITER",
    "KWH": "KWH", "MWH": "MWH",
}

def parse_sap_date(date_str):
    if not date_str or pd.isna(date_str):
        return None
    date_str = str(date_str).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None

def parse_sap_file(file_path):
    errors = []
    try:
        for sep in [";", "\t", ","]:
            try:
                df = pd.read_csv(file_path, sep=sep, encoding="utf-8-sig", dtype=str)
                if len(df.columns) > 3:
                    break
            except Exception:
                continue
    except Exception as e:
        return [], [f"Could not read file: {str(e)}"]

    df.rename(columns=SAP_COLUMN_MAP, inplace=True)
    df.dropna(how="all", inplace=True)
    df = df[~df.get("posting_date", pd.Series(dtype=str)).astype(str).str.contains("Summe|Total|Gesamt", na=False)]

    records = []
    for idx, row in df.iterrows():
        row_errors = []
        rec = {"_row_index": idx, "_raw": row.to_dict()}

        date_val = parse_sap_date(row.get("posting_date", ""))
        if not date_val:
            row_errors.append(f"Row {idx}: unparseable date '{row.get('posting_date')}'")
            date_val = parse_sap_date(row.get("document_date", ""))
        rec["activity_date"] = str(date_val) if date_val else None

        qty_raw = str(row.get("quantity", "")).replace(",", ".").replace(" ", "")
        try:
            rec["quantity"] = float(qty_raw)
        except ValueError:
            row_errors.append(f"Row {idx}: invalid quantity '{qty_raw}'")
            rec["quantity"] = None

        unit_raw = str(row.get("unit", "")).upper().strip()
        rec["unit"] = UNIT_NORMALIZATION.get(unit_raw, unit_raw or "KG")

        plant = str(row.get("plant_code", "")).strip()
        rec["facility_or_entity"] = PLANT_LOOKUP.get(plant, plant)

        mat_grp = str(row.get("material_group", "")).strip().upper()
        mapping = MATERIAL_GROUP_MAP.get(mat_grp, {"category": "Unknown", "scope": "SCOPE_3"})
        rec["category"] = mapping["category"]
        rec["scope"] = mapping["scope"]

        rec["activity_description"] = str(row.get("material_description", "")).strip()
        rec["source_type"] = "SAP"
        rec["parse_errors"] = row_errors
        errors.extend(row_errors)
        records.append(rec)

    return records, errors