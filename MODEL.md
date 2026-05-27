# MODEL.md — Data Model Documentation

## Overview

The data model is built around one core principle: **immutability of source data**. Every row ingested from any source is stored exactly as received before any transformation occurs. Analysts and auditors can always answer "what exactly did the client send us?" by looking at `RawRecord`. Normalized, computed values live in `EmissionRecord` — a derived view that can be corrected without ever touching the original.

---

## Entity Relationship Summary

```
Tenant
  └── IngestBatch (one upload event)
        ├── RawRecord (immutable source row × N)
        │     └── EmissionRecord (normalized, 1:1 with RawRecord)
        │           └── AuditLog (append-only change history)
        └── batch-level LLM summary (stored on IngestBatch.llm_summary)

EmissionFactor (global lookup table, used by RAG layer)
```

---

## Multi-Tenancy

Multi-tenancy is implemented at the **row level**: every table that holds client data has a `tenant_id` foreign key. Every query in the application filters by `tenant_id` before returning results.

**Why row-level and not schema-level?**
Schema-per-tenant (PostgreSQL schemas) would be more secure and easier to query, but it requires dynamic schema creation and more complex migrations. For a prototype on a shared Render instance, row-level isolation is sufficient and far simpler to reason about. The tradeoff is documented in `TRADEOFFS.md`.

---

## Tables

### `Tenant`
Represents a client company onboarded to the platform.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| name | VARCHAR | Company name |
| slug | SlugField | URL-safe identifier |
| created_at | DateTime | Onboarding timestamp |

---

### `IngestBatch`
One upload event — one file from one source. Tracks the lifecycle of an ingestion job.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| tenant | FK → Tenant | Scoped to client |
| source_type | ENUM | `sap` / `utility` / `travel` |
| original_filename | VARCHAR | Preserved for audit |
| uploaded_by | FK → User | Who triggered the upload |
| uploaded_at | DateTime | Upload timestamp |
| status | ENUM | `pending` / `processing` / `done` / `failed` |
| record_count | INT | Rows successfully parsed |
| error_count | INT | Rows that failed parsing |
| llm_summary | TEXT | LangGraph agent's natural language summary |
| processing_notes | TEXT | Parser warnings and diagnostics |

---

### `RawRecord`
**Immutable.** Stores the original row from the source file, unchanged. Never updated after creation.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| batch | FK → IngestBatch | Which upload produced this row |
| tenant | FK → Tenant | Denormalized for query performance |
| row_index | INT | Position in original file |
| raw_data | JSONB | Original row as-is (German headers, inconsistent units, all of it) |
| parse_error | TEXT | If the parser failed on this row, why |
| created_at | DateTime | Insertion timestamp |

**Why store the raw row as JSON?**
SAP exports arrive with column headers like `Buchungsdatum`, `Werk`, `Menge`. Utility CSVs have tariff codes and meter IDs. Travel JSON has IATA codes and cabin class codes. Rather than trying to map every possible field at ingest time, we store the full original row. If our normalizer has a bug, we can re-derive `EmissionRecord` from `RawRecord` without asking the client to re-send data.

---

### `EmissionRecord`
The normalized, analyst-reviewable view of a single emission activity. One-to-one with `RawRecord`.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| tenant | FK → Tenant | |
| raw_record | OneToOne → RawRecord | Source linkage — never null |
| batch | FK → IngestBatch | |
| scope | INT | 1, 2, or 3 (see Scope Assignment below) |
| category | ENUM | `fuel` / `procurement` / `electricity` / `flight` / `hotel` / `ground_transport` |
| source_type | ENUM | Mirrors batch source type |
| activity_description | VARCHAR | Human-readable description of the activity |
| activity_value | FLOAT | Quantity as reported in source |
| activity_unit_original | VARCHAR | Unit as reported (e.g. `L`, `MWh`, `kWh`) |
| activity_value_normalized | FLOAT | Quantity in base unit after normalization |
| activity_unit_normalized | VARCHAR | Base unit after normalization |
| emission_factor | FLOAT | kgCO2e per unit (from DEFRA 2023) |
| emission_factor_source | VARCHAR | Citation for the factor used |
| co2e_kg | FLOAT | `activity_value_normalized × emission_factor` |
| activity_date | Date | Date of the activity |
| billing_period_start | Date | For utility records: start of billing period |
| billing_period_end | Date | For utility records: end of billing period |
| facility_code | VARCHAR | SAP plant code |
| facility_name | VARCHAR | Human-readable facility name |
| country | CHAR(2) | ISO 3166-1 alpha-2 |
| origin_iata | CHAR(3) | Flight origin airport code |
| destination_iata | CHAR(3) | Flight destination airport code |
| distance_km | FLOAT | Calculated via Haversine formula from IATA codes |
| status | ENUM | `pending` / `approved` / `rejected` / `flagged` |
| reviewed_by | FK → User | Analyst who took action |
| reviewed_at | DateTime | When action was taken |
| analyst_note | TEXT | Analyst's free-text comment |
| is_anomaly | BOOL | Flagged by LangGraph anomaly detection agent |
| anomaly_reason | TEXT | LLM-generated explanation of the anomaly |
| created_at | DateTime | |
| updated_at | DateTime | Auto-updated on any change |

---

### `AuditLog`
**Append-only.** Every state change to an `EmissionRecord` produces one row here. Rows are never deleted or updated.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| emission_record | FK → EmissionRecord | |
| tenant | FK → Tenant | Denormalized for query performance |
| action | ENUM | `created` / `edited` / `approved` / `rejected` / `flagged` / `note_added` |
| performed_by | FK → User | |
| timestamp | DateTime | Auto-set on creation |
| before_snapshot | JSONB | Full record state before the change |
| after_snapshot | JSONB | Full record state after the change |
| note | TEXT | Optional free-text context |

**Why full snapshots instead of diffs?**
Diffs are compact but require replaying history to reconstruct any prior state. Full snapshots are larger but let auditors see exactly what a record looked like at any point in time with a single query. At the data volumes ESG reporting involves (thousands, not millions of rows), storage cost is negligible.

---

### `EmissionFactor`
Local emission factor store. Seeded from DEFRA 2023 greenhouse gas conversion factors. Used as the backing store for the RAG (Retrieval-Augmented Generation) layer — FAISS indexes this table so the LLM can retrieve the right factor for ambiguous activity descriptions.

| Field | Type | Notes |
|-------|------|-------|
| id | INT | Primary key |
| category | VARCHAR | Matches EmissionRecord.category |
| fuel_or_activity_type | VARCHAR | e.g. "diesel", "short-haul economy flight" |
| unit | VARCHAR | Unit the factor applies to |
| kgco2e_per_unit | FLOAT | The factor value |
| source | VARCHAR | Citation (e.g. "DEFRA 2023 Table 1a") |
| scope | INT | 1, 2, or 3 |
| notes | TEXT | Any caveats on applicability |

---

## Scope Assignment Logic

Scope is assigned deterministically at parse time based on source type and category:

| Source | Category | Scope | Rationale |
|--------|----------|-------|-----------|
| SAP | fuel | 1 | Direct combustion of fuel owned/controlled by the reporting entity |
| SAP | procurement | 3 | Upstream emissions from purchased goods |
| Utility | electricity | 2 | Purchased electricity — indirect, location-based |
| Travel | flight | 3 | Business travel in assets not owned by entity |
| Travel | hotel | 3 | Business travel — upstream value chain |
| Travel | ground_transport | 3 | Business travel |

This follows the GHG Protocol Corporate Standard (2004, updated 2015).

---

## Unit Normalization

All values are normalized to a base unit before `co2e_kg` is calculated:

| Category | Original units seen | Normalized to |
|----------|-------------------|---------------|
| Fuel | L, gal, m³ | Liters (L) |
| Electricity | kWh, MWh, GWh | kWh |
| Flight | km, miles, (IATA codes → Haversine) | km |
| Hotel | nights | nights |
| Ground transport | km, miles | km |

The original value and unit are always preserved in `activity_value` and `activity_unit_original`.

---

## Source-of-Truth Tracking

Every `EmissionRecord` links to exactly one `RawRecord` via a non-nullable OneToOne foreign key. The `RawRecord` links to an `IngestBatch` which records the filename, upload timestamp, and uploader. This chain answers:

- Which file produced this emission record? → `EmissionRecord.batch.original_filename`
- What did the source row actually say? → `EmissionRecord.raw_record.raw_data`
- Who uploaded it and when? → `EmissionRecord.batch.uploaded_by`, `uploaded_at`
- Has this record been edited since ingestion? → `EmissionRecord.audit_logs` where `action = 'edited'`
- What did it look like before the edit? → `AuditLog.before_snapshot`
