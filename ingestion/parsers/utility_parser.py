import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

UNIT_CONVERSIONS = {
    "kwh": ("KWH", 1.0),
    "kw·h": ("KWH", 1.0),
    "mwh": ("MWH", 1000.0),
    "therm": ("THERM", None),
    "therms": ("THERM", None),
    "ccf": ("THERM", 1.0204),
    "btu": ("KWH", 0.000293071),
    "mmbtu": ("MMBTU", None),
}

COLUMN_ALIASES = {
    "start_date": ["start date", "period start", "from", "bill start", "service from", "startdate"],
    "end_date": ["end date", "period end", "to", "bill end", "service to", "enddate"],
    "consumption": ["consumption", "usage", "kwh", "quantity", "energy", "amount used", "net usage"],
    "unit": ["unit", "units", "uom", "unit of measure"],
    "meter_id": ["meter id", "meter number", "meter #", "account", "service point"],
}


def _find_column(df_columns, aliases):
    df_lower = {c.lower().strip(): c for c in df_columns}
    for alias in aliases:
        if alias.lower() in df_lower:
            return df_lower[alias.lower()]
    return None


def parse_utility_date(date_str):
    if not date_str or pd.isna(date_str):
        return None
    date_str = str(date_str).strip()
    if not date_str or date_str.lower() == "nan":
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def parse_utility_file(file_path):
    errors = []

    try:
        df = pd.read_csv(file_path, dtype=str, encoding="utf-8-sig")
    except Exception as e:
        return [], [f"Could not read file: {str(e)}"]

    df.dropna(how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Map column names using aliases
    col_map = {}
    for field, aliases in COLUMN_ALIASES.items():
        found = _find_column(df.columns.tolist(), aliases)
        if found:
            col_map[field] = found

    records = []
    for idx, row in df.iterrows():
        row_errors = []
        rec = {"_row_index": idx, "_raw": row.to_dict()}

        # ── Dates ──────────────────────────────────────────────────────────
        raw_start = row.get(col_map.get("start_date", ""), "") or ""
        raw_end   = row.get(col_map.get("end_date", ""), "") or ""

        period_start = parse_utility_date(str(raw_start).strip())
        period_end   = parse_utility_date(str(raw_end).strip())

        # Graceful fallbacks — never crash on missing dates
        if period_start and not period_end:
            period_end = period_start
            row_errors.append(f"Row {idx}: missing end date — using start date as fallback")
        elif period_end and not period_start:
            period_start = period_end
            row_errors.append(f"Row {idx}: missing start date — using end date as fallback")
        elif not period_start and not period_end:
            row_errors.append(f"Row {idx}: both billing period dates missing")

        rec["activity_date"] = str(period_end)   if period_end   else None
        rec["period_start"]  = str(period_start) if period_start else None
        rec["period_end"]    = str(period_end)   if period_end   else None

        # ── Consumption ────────────────────────────────────────────────────
        raw_qty = str(row.get(col_map.get("consumption", ""), "") or "").replace(",", "").strip()
        try:
            rec["quantity"] = float(raw_qty)
        except ValueError:
            row_errors.append(f"Row {idx}: invalid consumption value '{raw_qty}'")
            rec["quantity"] = None

        # ── Unit ───────────────────────────────────────────────────────────
        unit_raw = str(row.get(col_map.get("unit", ""), "") or "kwh").lower().strip()
        rec["unit"] = UNIT_CONVERSIONS.get(unit_raw, ("KWH", 1.0))[0]

        # ── Meter / facility ───────────────────────────────────────────────
        meter = str(row.get(col_map.get("meter_id", ""), "") or "").strip()
        rec["facility_or_entity"] = meter

        # ── Fixed fields ───────────────────────────────────────────────────
        rec["activity_description"] = f"Electricity consumption — Meter {meter}"
        rec["category"]   = "Electricity"
        rec["scope"]      = "SCOPE_2"
        rec["source_type"] = "UTILITY"
        rec["parse_errors"] = row_errors
        errors.extend(row_errors)
        records.append(rec)

    return records, errors