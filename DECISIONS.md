# DECISIONS.md — Design Decisions and Tradeoffs

This document records every significant ambiguity I encountered and how I resolved it.

---

## Source 1: SAP (Fuel and Procurement)

### Decision: Flat file CSV export, not IDoc or OData

**Options considered:**
- **IDoc (Intermediate Document):** SAP's native EDI format. XML-based, message types like `MATMAS05` or `MBGMCR`. Highly structured but requires a live SAP system and EDI middleware to produce. No sustainability team emails you an IDoc.
- **OData service:** SAP Gateway exposes data via REST/OData. Clean API, but requires SAP Netweaver Gateway configuration and an active connection. Not realistic for a client onboarding scenario.
- **BAPI:** SAP function modules callable via RFC. Same problem — requires live system access.
- **Flat file (CSV/XLSX) export:** Produced via SAP transaction MB51 (material document list) or ME2M (purchase orders). This is what a sustainability manager actually does — runs a transaction, exports to CSV, emails it or uploads it to a portal.

**Choice: Flat file CSV from MB51/ME2M transaction.**

**Why:** This is the realistic ingestion path for enterprise clients without API access. The sustainability lead runs MB51, filters by movement type (261 = goods issue for production, relevant for fuel consumption), exports. The resulting file has columns like `Buchungsdatum` (posting date), `Werk` (plant), `Menge` (quantity), `Mengeneinheit` (unit of measure), `Material` (material number).

**What I handle:** Movement type 261 (fuel consumption), columns mapped from German headers, date format DD.MM.YYYY, units in L/m³/kg normalized to liters. Plant codes looked up against a hardcoded plant-to-facility mapping (a real deployment would have this as a configurable lookup table).

**What I ignore:** Goods receipts, stock transfers, procurement categories beyond direct fuel. IDoc ingestion entirely. SAP S/4HANA's newer column formats.

**What I'd ask the PM:** "Does the client have SAP Fiori? If so we can get a cleaner export. What movement types are relevant for their fuel tracking — just 261 or also 101/102?"

---

### Decision: LLM-assisted column mapping for SAP headers

SAP exports in German configurations have column headers that vary by SAP version, language settings, and transaction. Rather than maintaining a brittle lookup table of every possible header variant, I use a LangChain LLM call to map incoming headers to our schema fields.

**Why:** A lookup table breaks the moment a client upgrades SAP or changes language settings. The LLM handles "Buchungsdatum", "Posting Date", "Belegdatum" all correctly without code changes.

**What I'd ask the PM:** "Can we get a data dictionary from the client's SAP team? That would let us validate the LLM mapping and catch edge cases before go-live."

---

## Source 2: Utility (Electricity)

### Decision: Portal CSV export, not PDF bill or utility API

**Options considered:**
- **PDF bill parsing:** Most utilities send PDF invoices. PDF parsing is fragile — layout changes break parsers, tables are inconsistently structured, scanned PDFs require OCR. High maintenance cost.
- **Utility API:** Green Button (US standard), ESPI protocol, or utility-specific APIs (EDF, E.ON). Available only for large commercial accounts with API agreements. Not realistic for most enterprise clients.
- **Portal CSV export:** Every major utility (PG&E, ComEd, EDF, BESCOM) has a customer portal with "Download Usage Data" that exports a CSV. This is the most universally available option requiring no special agreements.

**Choice: Portal CSV export.**

**Why:** It's the path of least resistance for the facilities team. "Log into the utility portal, go to Usage, click Download, upload here" is a workflow any facilities manager can follow. It also gives us structured data (unlike PDF) without requiring API agreements (unlike utility APIs).

**What the CSV typically contains:** Account number, service address, billing period start/end, meter reading start/end, consumption (kWh or MWh), demand (kW), tariff code, charges. Critically, billing periods don't align to calendar months — a billing period might be Dec 18 to Jan 22.

**How I handle billing period misalignment:** I store `billing_period_start` and `billing_period_end` on the `EmissionRecord`. For monthly reporting, emissions are prorated across the months the billing period spans. This is noted as a known limitation — a real implementation would need a more sophisticated time-series allocation.

**What I'd ask the PM:** "Which utilities does this client use? If they're on BESCOM (Bangalore) the portal CSV format is different from PG&E. Do we need to handle multiple meters across facilities?"

---

## Source 3: Corporate Travel

### Decision: JSON format modeled on Concur/Navan API response

**Options considered:**
- **Concur SAP API:** Well-documented REST API, returns trip segments as JSON. Requires OAuth setup with the client's Concur instance.
- **Navan API:** Similar structure, newer platform, growing enterprise adoption.
- **Manual CSV export:** Both platforms support CSV exports from their reporting modules.

**Choice: JSON file upload modeled on Concur/Navan trip segment structure.**

**Why:** The JSON structure from both platforms is well-documented and consistent enough to design against. A real deployment would pull directly from the API; for the prototype, uploading a JSON file that matches the API response shape demonstrates we understand the real data format without needing OAuth credentials.

**The realistic data shape:**
```json
{
  "trips": [{
    "trip_id": "T-001",
    "employee_id": "E-123",
    "segments": [{
      "type": "flight",
      "origin_iata": "BLR",
      "destination_iata": "DEL",
      "departure_date": "2024-01-15",
      "cabin_class": "economy",
      "carrier": "6E"
    }, {
      "type": "hotel",
      "property_name": "Taj Delhi",
      "check_in": "2024-01-15",
      "check_out": "2024-01-17",
      "city": "Delhi",
      "country": "IN"
    }]
  }]
}
```

**Distance calculation:** Concur doesn't always provide distance. When only IATA codes are given, I calculate great-circle distance using the Haversine formula with a standard airport coordinates lookup table, then apply a route factor of 1.08 (ICAO recommendation for non-direct routing).

**Emission factors applied:**
- Short-haul economy (<3700km): 0.255 kgCO2e/km/passenger (DEFRA 2023)
- Long-haul economy (≥3700km): 0.195 kgCO2e/km/passenger (DEFRA 2023)
- Business class multiplier: 2.0x
- Hotel: 20.6 kgCO2e/room-night (DEFRA 2023 average)
- Ground transport (taxi/rideshare): 0.149 kgCO2e/km

**What I'd ask the PM:** "Does the client use Concur or Navan? Can we get API credentials for a direct pull rather than file upload? Do they track personal car use for business travel or only booked travel?"

---

## LLM / RAG Integration

### Decision: Use Gemini (not OpenAI) for LLM calls

**Why:** The project already had `langchain-google-genai` in the stack from prior work. Gemini 1.5 Flash is fast and cost-effective for the parsing tasks we need (column mapping, anomaly summarization). Using a consistent LLM throughout reduces API key management complexity.

### Decision: LangGraph for the review agent, not a simple LangChain chain

The anomaly detection and batch summarization workflow has branching logic: if anomalies are found, generate detailed explanations; if the batch is clean, generate a summary; if parsing failed, explain why. LangGraph's state machine model fits this branching better than a linear chain.

**Graph nodes:**
1. `parse_batch` — check parse results
2. `detect_anomalies` — statistical checks (values > 3σ from mean, unit inconsistencies)
3. `summarize_anomalies` — LLM generates analyst-readable explanation per anomaly
4. `generate_batch_summary` — LLM produces overall batch summary
5. `write_results` — persist summaries back to database

### Decision: FAISS for vector store, not Pinecone or Weaviate

**Why:** FAISS runs in-process with no external service dependency. For a prototype with ~200 emission factor entries, an in-memory FAISS index is sufficient. A production deployment would move to a managed vector store, but adding an external vector DB would introduce another deployment dependency and potential failure point for a 4-day assignment.

---

## Review Workflow

### Decision: Four statuses (pending / approved / rejected / flagged), not two (approved / rejected)

**Why:** Analysts need a way to mark records that need attention without making a final decision. `flagged` means "I've seen this, something looks wrong, needs discussion before approval." `pending` means "not yet reviewed." These are meaningfully different states in a real audit workflow.

### Decision: Approved records are not editable

Once a record is approved, the analyst cannot change its values (only add a note). To correct an approved record, they must reject it and re-approve after editing. This creates a cleaner audit trail — auditors can see that a correction was made explicitly, not silently.

---

## Multi-tenancy

### Decision: Row-level isolation, not schema-per-tenant

Every table has `tenant_id`. All queries filter by it. A middleware layer enforces this — views receive the tenant from the authenticated user's profile, not from the URL.

**What I'd ask the PM before production:** "Are there regulatory requirements for data isolation between clients? GDPR or SOC2 compliance requirements might mandate schema-level or database-level isolation."

---

## Deployment

### Decision: SQLite for prototype, PostgreSQL for production

The prototype uses SQLite locally and on Render (via `dj-database-url` defaulting to SQLite if `DATABASE_URL` is not set). SQLite resets on Render free tier restarts, which is acceptable for a demo.

A production deployment would use Render's managed PostgreSQL or equivalent. The `dj-database-url` configuration means the switch requires only setting the `DATABASE_URL` environment variable — no code changes.

### Decision: Django serves the React build (single deployment)

Rather than deploying frontend and backend separately, the React build is served as static files by Django/WhiteNoise. This means one URL, one deployment, one set of credentials to share with the graders. The tradeoff (no CDN for static assets, Django handles all requests) is acceptable for a demo.
