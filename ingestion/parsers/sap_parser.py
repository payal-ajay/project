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
    "PL01": "Manufacturing Plant A", "PL02": "Manufacturing Plant B",
    "PL03": "Logistics Center", "PL00": "Corporate HQ",
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

ENERGY_TYPE_MAP = {
    "electricity (grid)":       {"category": "Electricity", "scope": "SCOPE_2"},
    "natural gas":              {"category": "Natural Gas", "scope": "SCOPE_1"},
    "renewable energy (solar)": {"category": "Solar Energy", "scope": "SCOPE_2"},
    "renewable energy (wind)":  {"category": "Wind Energy", "scope": "SCOPE_2"},
    "diesel (generators)":      {"category": "Diesel", "scope": "SCOPE_1"},
    "diesel (fleet)":           {"category": "Diesel Fleet", "scope": "SCOPE_1"},
}

SCOPE_MAP = {
    "scope 1": "SCOPE_1",
    "scope 2": "SCOPE_2",
    "scope 3": "SCOPE_3",
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


def _is_multisection(df):
    """Only check first 5 rows to detect section markers."""
    first_col = df.iloc[:5, 0].astype(str)
    return first_col.str.contains("SECTION|===", regex=True, na=False).any()


def _parse_standard_sap(df):
    """Parse standard MB51/ME2M SAP flat file."""
    df = df.rename(columns=SAP_COLUMN_MAP)
    df = df.dropna(how="all")
    df = df.reset_index(drop=True)

    if "posting_date" in df.columns:
        mask = ~df["posting_date"].astype(str).str.contains(
            "Summe|Total|Gesamt|===|\\*\\*\\*", na=False, regex=True
        )
        df = df[mask].reset_index(drop=True)

    records, errors = [], []
    for idx, row in df.iterrows():
        row_errors = []
        rec = {"_row_index": idx, "_raw": row.to_dict()}

        # Date — try posting date first, fall back to document date
        date_val = parse_sap_date(row.get("posting_date", ""))
        if not date_val:
            row_errors.append(f"Row {idx}: missing posting date, using document date")
            date_val = parse_sap_date(row.get("document_date", ""))
        rec["activity_date"] = str(date_val) if date_val else None

        # Quantity — handle European decimal comma
        qty_raw = str(row.get("quantity", "")).replace(",", ".").replace(" ", "").strip()
        try:
            rec["quantity"] = float(qty_raw)
        except ValueError:
            row_errors.append(f"Row {idx}: invalid quantity '{qty_raw}'")
            rec["quantity"] = None

        # Unit
        unit_raw = str(row.get("unit", "")).upper().strip()
        rec["unit"] = UNIT_NORMALIZATION.get(unit_raw, unit_raw or "KG")

        # Plant → facility name
        plant = str(row.get("plant_code", "")).strip()
        rec["facility_or_entity"] = PLANT_LOOKUP.get(plant, plant or "Unknown Plant")

        # Material group → category + scope
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


def _process_energy_section(headers, rows, start_idx):
    records, errors = [], []
    MONTH_COLS = {
        "Jan-2025": "2025-01-31", "Feb-2025": "2025-02-28",
        "Mar-2025": "2025-03-31", "Apr-2025": "2025-04-30",
    }
    for i, row in enumerate(rows):
        if len(row) < 6:
            continue
        row_dict = dict(zip(headers, row))
        energy_type = row_dict.get("Energy Type", "").lower().strip()
        unit_raw = row_dict.get("Unit", "MWh").upper().strip()
        plant = row_dict.get("Plant", "")
        cost_center_name = row_dict.get("Cost Center Name", "")
        mapping = ENERGY_TYPE_MAP.get(energy_type, {"category": energy_type.title(), "scope": "SCOPE_2"})

        for month_col, date_str in MONTH_COLS.items():
            qty_raw = row_dict.get(month_col, "").replace(",", "").strip()
            if not qty_raw or qty_raw in ("nan", ""):
                continue
            try:
                qty = float(qty_raw)
            except ValueError:
                continue
            records.append({
                "_row_index": start_idx + i,
                "_raw": row_dict,
                "activity_date": date_str,
                "quantity": qty,
                "unit": UNIT_NORMALIZATION.get(unit_raw, unit_raw),
                "category": mapping["category"],
                "scope": mapping["scope"],
                "facility_or_entity": PLANT_LOOKUP.get(plant, cost_center_name),
                "activity_description": f"{mapping['category']} — {cost_center_name} ({month_col})",
                "source_type": "SAP",
                "parse_errors": [],
            })
    return records, errors


def _process_ghg_section(headers, rows, start_idx):
    records, errors = [], []
    MONTH_COLS = {
        "Jan-2025": "2025-01-31", "Feb-2025": "2025-02-28",
        "Mar-2025": "2025-03-31", "Apr-2025": "2025-04-30",
    }
    for i, row in enumerate(rows):
        if len(row) < 6:
            continue
        row_dict = dict(zip(headers, row))
        scope_raw = row_dict.get("Emission Scope", "").lower().strip()
        scope = SCOPE_MAP.get(scope_raw, "SCOPE_3")
        category = row_dict.get("Emission Category", "GHG Emission")
        ghg_type = row_dict.get("GHG Type", "CO2")
        cost_center_name = row_dict.get("Cost Center Name", "")
        unit_raw = row_dict.get("Unit", "tCO2e").strip()

        for month_col, date_str in MONTH_COLS.items():
            qty_raw = row_dict.get(month_col, "").replace(",", "").strip()
            if not qty_raw or qty_raw in ("nan", ""):
                continue
            try:
                qty = float(qty_raw)
            except ValueError:
                continue
            qty_kg = qty * 1000 if "tco2" in unit_raw.lower() else qty
            records.append({
                "_row_index": start_idx + i,
                "_raw": row_dict,
                "activity_date": date_str,
                "quantity": qty,
                "unit": "TONNE",
                "quantity_co2e_kg": qty_kg,
                "emission_factor_used": "Direct GHG measurement (SAP ESG Report)",
                "emission_factor_source": "SAP S/4HANA ESG Module",
                "category": f"{category} ({ghg_type})",
                "scope": scope,
                "facility_or_entity": cost_center_name,
                "activity_description": f"{scope_raw.title()} — {category} ({ghg_type}) — {cost_center_name} ({month_col})",
                "source_type": "SAP",
                "parse_errors": [],
            })
    return records, errors


def _parse_multisection_esg(file_path):
    records, errors = [], []
    row_idx = 0
    try:
        raw = pd.read_csv(file_path, header=None, dtype=str, encoding="utf-8-sig")
    except Exception as e:
        return [], [f"Could not read file: {e}"]

    current_section = None
    section_header = None
    section_rows = []

    for _, row in raw.iterrows():
        first_cell = str(row.iloc[0]).strip()

        if "SECTION 1" in first_cell and "ENERGY" in first_cell.upper():
            current_section = "ENERGY"
            section_header = None
            section_rows = []
            continue
        elif "SECTION 2" in first_cell and "GHG" in first_cell.upper():
            if section_rows and section_header is not None:
                r, e = _process_energy_section(section_header, section_rows, row_idx)
                records.extend(r); errors.extend(e); row_idx += len(r)
            current_section = "GHG"
            section_header = None
            section_rows = []
            continue
        elif first_cell.startswith("===") and current_section in ("ENERGY", "GHG"):
            if section_rows and section_header is not None:
                fn = _process_energy_section if current_section == "ENERGY" else _process_ghg_section
                r, e = fn(section_header, section_rows, row_idx)
                records.extend(r); errors.extend(e); row_idx += len(r)
            current_section = None
            section_header = None
            section_rows = []
            continue

        if current_section in ("ENERGY", "GHG"):
            if row.isna().all() or all(str(v).strip() in ("", "nan") for v in row):
                continue
            if section_header is None:
                section_header = [str(v).strip() for v in row]
            else:
                section_rows.append([str(v).strip() for v in row])

    if section_rows and section_header is not None and current_section in ("ENERGY", "GHG"):
        fn = _process_energy_section if current_section == "ENERGY" else _process_ghg_section
        r, e = fn(section_header, section_rows, row_idx)
        records.extend(r); errors.extend(e)

    return records, errors


def parse_sap_file(file_path):
    """
    Auto-detects SAP file type:
    - Multi-section ESG report → section parser
    - Standard MB51/ME2M flat file → standard parser
    """
    try:
        for sep in [";", "\t", ","]:
            try:
                df = pd.read_csv(file_path, sep=sep, encoding="utf-8-sig", dtype=str, header=None)
                if len(df.columns) > 3:
                    break
            except Exception:
                continue
    except Exception as e:
        return [], [f"Could not read file: {str(e)}"]

    if _is_multisection(df):
        return _parse_multisection_esg(file_path)

    # Re-read with headers for standard parser
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

    return _parse_standard_sap(df)