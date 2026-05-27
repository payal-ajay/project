# SOURCES.md — Data Source Research

For each of the three sources: what I researched, what I learned, what my sample data looks like and why, and what would break in a real deployment.

---

## Source 1: SAP Export (Fuel and Procurement)

### What I researched

SAP is not a single thing — it's a platform with hundreds of modules, each producing data differently. For fuel and procurement tracking relevant to Scope 1 emissions, the relevant SAP modules are:

- **MM (Materials Management):** Tracks goods movements. Transaction MB51 produces a material document list. Movement type 261 = goods issue for production (consumption of fuel). Movement type 101 = goods receipt (procurement).
- **FI (Financial Accounting):** Can produce procurement spend reports but doesn't have quantity data needed for emission calculations.
- **PM (Plant Maintenance):** Tracks maintenance orders which can consume fuel.

I focused on **MB51 exports** because:
1. They contain quantity and unit data, not just monetary values
2. Movement type 261 directly represents fuel consumption
3. The export is available to sustainability teams without IT involvement

**What an MB51 export actually looks like:**

SAP generates flat files with semicolon or tab delimiters. In German-language SAP installations (common for European manufacturers), column headers are in German. The same export in English SAP has different headers. Key columns:

| German header | English equivalent | Notes |
|---------------|-------------------|-------|
| Buchungsdatum | Posting Date | Format: DD.MM.YYYY |
| Werk | Plant | 4-character plant code (e.g. "1000", "DE01") |
| Material | Material Number | SAP material master number |
| Materialkurztext | Material Description | e.g. "Diesel kraftstoff", "Erdgas" |
| Menge | Quantity | Numeric, uses comma as decimal separator in German locale |
| Mengeneinheit | Unit of Measure | SAP internal codes: "L" (liters), "M3" (cubic meters), "KG" (kilograms), "TO" (metric tons) |
| Bewegungsart | Movement Type | 261 = consumption, 101 = receipt |
| Kostenstelle | Cost Center | Maps to facility/department |

**Date format trap:** German SAP uses `15.01.2024`, not `2024-01-15`. The parser must handle both.

**Decimal separator trap:** German locale uses comma as decimal separator: `1.234,56` means 1234.56. A naive `float()` call will fail.

**Plant code problem:** "1000" or "DE01" means nothing without a plant master data table that maps codes to facility names and locations. In a real deployment, we'd need this lookup table from the client's SAP team.

### What my sample data looks like and why

```csv
Buchungsdatum;Werk;Material;Materialkurztext;Menge;Mengeneinheit;Bewegungsart;Kostenstelle
15.01.2024;1000;100-400;Diesel kraftstoff;2.500,00;L;261;KOST-001
22.01.2024;1000;100-400;Diesel kraftstoff;1.800,00;L;261;KOST-001
05.02.2024;2000;100-401;Erdgas;450,00;M3;261;KOST-002
18.02.2024;1000;100-402;Heizöl EL;3.200,00;L;261;KOST-001
```

I used:
- German column headers (realistic for a European manufacturing client)
- German decimal format (comma separator)
- DD.MM.YYYY dates
- Real SAP material description conventions ("kraftstoff" = fuel, "Erdgas" = natural gas, "Heizöl EL" = heating oil extra light)
- Two plants (1000 and 2000) to demonstrate multi-facility handling
- Movement type 261 throughout (consumption)

### What would break in a real deployment

1. **Plant code lookup table:** We hardcode a small mapping. A real client has 50+ plants. We'd need to ingest their plant master data first.
2. **Material number mapping:** "100-400" is meaningless without the client's material master. Different clients number diesel differently.
3. **Locale variations:** Not all SAP installations use German locale even in German companies. Some use English headers with German decimal formats. The parser needs to detect and handle this.
4. **Fiscal year vs calendar year:** SAP's posting dates follow fiscal year logic. A client with April-March fiscal year has data that doesn't align to calendar year reporting periods.
5. **Multiple movement types:** A real fuel tracking implementation needs to handle receipts (101), returns (102), and consumption (261) together to calculate net consumption, not just raw issue quantities.

---

## Source 2: Utility Portal CSV (Electricity)

### What I researched

I looked at the download formats for several major utilities:

- **BESCOM (Bangalore):** Customer portal exports billing data as CSV with columns: Consumer Number, Service Address, Billing Month, Units Consumed (kWh), Demand (kVA), Amount
- **PG&E (California):** Green Button CSV format — standardized US format with: Date, Start Time, Duration, Consumption (kWh)
- **EDF (UK):** Portal exports: Account, Meter Serial, Read Date, Read Type, Units, kWh
- **ComEd (Illinois):** Similar to PG&E, Green Button compliant

**Key insights from this research:**

1. **Billing periods don't align to calendar months.** BESCOM bills on a 30-35 day cycle starting from meter read date, not calendar month. A "January" bill might cover Dec 18 to Jan 22.

2. **Units vary.** Smaller commercial accounts are billed in kWh. Large industrial accounts are billed in MWh or even in units of 100 kWh. Some utilities mix demand (kVA/kW) and consumption (kWh) in the same export.

3. **Tariff codes matter.** Commercial tariff (LT-4), industrial tariff (HT-2), etc. Different tariffs have different time-of-use structures. For Scope 2 location-based calculation this doesn't matter (we just need kWh), but for market-based Scope 2 with RECs it becomes relevant.

4. **Multiple meters per facility.** A large facility might have 5-10 meter connections. The export has one row per meter per billing period, not one row per facility per month.

### What my sample data looks like and why

```csv
account_number,service_address,meter_serial,billing_period_start,billing_period_end,consumption_kwh,demand_kva,tariff_code,amount_inr
ACC-001,Plot 47 KIADB Industrial Area Bangalore,MTR-001,2024-01-03,2024-02-01,48250,180,LT-4B,385000
ACC-001,Plot 47 KIADB Industrial Area Bangalore,MTR-002,2024-01-05,2024-02-03,12400,45,LT-4B,98000
ACC-002,Survey No 112 Peenya Industrial Area,MTR-003,2023-12-28,2024-01-30,67800,240,HT-2,542000
ACC-001,Plot 47 KIADB Industrial Area Bangalore,MTR-001,2024-02-01,2024-03-02,51200,185,LT-4B,410000
```

I used:
- BESCOM-style format (Indian utility, relevant given the client context)
- Billing periods that cross month boundaries (Dec 28 to Jan 30)
- Multiple meters per account (MTR-001 and MTR-002 for ACC-001)
- Real tariff codes (LT-4B = Low Tension commercial, HT-2 = High Tension industrial)
- Amounts in INR (Indian Rupees) — not used for emission calculation but preserved in raw data

### What would break in a real deployment

1. **Billing period proration:** When a billing period spans two calendar months, we need to prorate the consumption. Our prototype assigns all consumption to the `activity_date` (billing period end). A real implementation needs time-series allocation.
2. **Multiple meters:** Our prototype creates one `EmissionRecord` per row. Aggregating to facility level for reporting requires grouping by `facility_code` across meters — we support this in queries but don't expose it in the UI yet.
3. **Grid emission factor by region and year:** We use a single India grid factor (0.82 kgCO2e/kWh, CEA 2022). A multi-country client needs region-specific factors. The UK grid factor (0.21 kgCO2e/kWh) is very different from India's.
4. **Demand vs consumption:** Some utility exports give cumulative meter readings, not consumption directly. We'd need to calculate `consumption = current_reading - previous_reading` which requires ordered historical data.

---

## Source 3: Corporate Travel JSON (Concur/Navan)

### What I researched

I reviewed the Concur Travel API documentation (SAP Concur Developer Center) and Navan's API documentation.

**Concur Travel Itinerary API** (`/api/travel/trip/v1.1`):
- Returns trips as XML or JSON
- Each trip has segments: Air, Car, Hotel, Rail
- Air segments include: origin, destination, departure/arrival datetime, cabin class, carrier, flight number
- Distance is sometimes included, sometimes not
- Booking class (economy/business/first) is always present

**Navan API** (similar structure, REST/JSON):
- Trip object with `segments` array
- Each segment has `type`, origin/destination codes, dates, and category-specific fields
- Hotel segments include property name, city, country, check-in/check-out dates
- Ground transport includes pickup/dropoff and estimated distance

**Key insight on distances:**
Neither platform consistently provides distances. Concur includes distance for car rentals but not always for flights. When only IATA codes are present, distance must be calculated. I use the Haversine formula with a standard IATA airport coordinates database and apply ICAO's 1.08 indirect routing factor.

**Emission factors researched:**
From DEFRA 2023 Greenhouse Gas Conversion Factors (Appendix on Business Travel):
- Domestic flight (UK): 0.24517 kgCO2e/passenger-km (includes radiative forcing)
- Short-haul international economy: 0.15553 kgCO2e/passenger-km
- Long-haul international economy: 0.19085 kgCO2e/passenger-km
- Business class multiplier: 2.0× (occupies more space per passenger)
- First class multiplier: 2.4×
- Average hotel (UK): 20.6 kgCO2e/room-night
- Taxi: 0.14878 kgCO2e/km

Note: I used DEFRA 2023 factors throughout for consistency. ICAO CORSIA factors are an alternative for aviation but are optimized for airline-level reporting, not corporate travel.

### What my sample data looks like and why

```json
{
  "export_date": "2024-02-01",
  "company_id": "CORP-001",
  "trips": [
    {
      "trip_id": "T-2024-001",
      "employee_id": "EMP-042",
      "department": "Engineering",
      "segments": [
        {
          "type": "flight",
          "origin_iata": "BLR",
          "destination_iata": "BOM",
          "departure_date": "2024-01-10",
          "cabin_class": "economy",
          "carrier": "6E",
          "flight_number": "6E-456"
        },
        {
          "type": "hotel",
          "property_name": "Marriott Mumbai",
          "check_in": "2024-01-10",
          "check_out": "2024-01-12",
          "city": "Mumbai",
          "country": "IN"
        },
        {
          "type": "flight",
          "origin_iata": "BOM",
          "destination_iata": "BLR",
          "departure_date": "2024-01-12",
          "cabin_class": "economy",
          "carrier": "6E",
          "flight_number": "6E-789"
        }
      ]
    },
    {
      "trip_id": "T-2024-002",
      "employee_id": "EMP-017",
      "department": "Sales",
      "segments": [
        {
          "type": "flight",
          "origin_iata": "DEL",
          "destination_iata": "LHR",
          "departure_date": "2024-01-15",
          "cabin_class": "business",
          "carrier": "AI",
          "flight_number": "AI-111"
        },
        {
          "type": "hotel",
          "property_name": "Hilton London",
          "check_in": "2024-01-15",
          "check_out": "2024-01-18",
          "city": "London",
          "country": "GB"
        },
        {
          "type": "ground_transport",
          "mode": "taxi",
          "pickup_city": "London",
          "dropoff_city": "London",
          "distance_km": 22.5,
          "date": "2024-01-16"
        }
      ]
    }
  ]
}
```

I used:
- Indian domestic route (BLR→BOM, realistic Indigo flight)
- International long-haul (DEL→LHR, Air India) with business class to demonstrate the class multiplier
- Hotel stays with real property names
- Ground transport with explicit distance (not always available — testing the happy path)
- A round-trip structure (segment 1 and segment 3 of trip T-2024-001) to show that each segment becomes its own `EmissionRecord`

### What would break in a real deployment

1. **No distance on all flights:** Our Haversine calculation works for point-to-point. Connecting flights (BLR→DEL→LHR) require summing segment distances, not calculating direct BLR→LHR distance.
2. **Employee anonymization:** A real deployment needs to aggregate by department, not employee ID, for privacy. We store `employee_id` in `raw_data` but don't expose it in the analyst UI.
3. **Concur vs Navan schema differences:** Concur's actual API returns XML by default and has a different field naming convention. Our JSON parser assumes Navan-style naming. A real integration would need source-specific adapters.
4. **Currency and booking class normalization:** Concur uses booking class codes (Y, B, C, F) not "economy/business/first" strings. Mapping booking class to cabin class requires a carrier-specific lookup table.
5. **Radiative forcing:** DEFRA 2023 includes radiative forcing in aviation factors (multiplier ~1.9×). Some clients want factors without RF for comparison to IPCC figures. We use RF-inclusive factors throughout — this should be configurable.
