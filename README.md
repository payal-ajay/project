# Breathe ESG — Data Ingestion & Review Platform

A Django + React prototype built as part of a technical internship assignment for [Breathe ESG](https://www.breatheesg.com). The platform ingests emission activity data from three enterprise source types, normalizes it, runs AI-powered anomaly detection, and surfaces a review dashboard where analysts can approve or reject records before they're locked for audit.

---

## Live Demo

**Deployed app:** `https://your-render-url.onrender.com`
**Frontend:** `https://your-vercel-url.vercel.app`

Login not required for the demo — uses a default tenant.

---

## What It Does

Enterprise clients generate emissions data from many disconnected sources. This platform handles three of the most common:

| Source | Format | Real-world shape |
|---|---|---|
| SAP (fuel & procurement) | CSV flat file | MB51 / ME2M transaction export, German column headers, DD.MM.YYYY dates |
| Utility portal (electricity) | CSV | Billing periods that don't align to calendar months, mixed units (kWh, MWh, therms) |
| Corporate travel (flights, hotels, ground) | JSON | Concur/Navan-style segment data, IATA codes without distances |

After ingestion, every record goes through:
1. **Rule-based anomaly detection** — flags statistical outliers (>3σ from batch mean), zero/negative quantities, missing dates
2. **LangGraph review pipeline** — three-node graph: anomaly check → Gemini LLM analysis → batch summary
3. **Analyst review queue** — approve, reject, edit with full audit trail
4. **Export** — download structured data as CSV or JSON at any time

---

## Architecture

```
File Upload
    ↓
Parser (SAP / Utility / Travel)
    ↓
RawRecord (immutable — source of truth)
    ↓
LangGraph Pipeline
    ├── Node 1: Rule-based anomaly detection
    ├── Node 2: Gemini LLM flags suspicious rows
    └── Node 3: Plain-English batch summary
    ↓
EmissionRecord (normalized — analyst-facing)
    ↓
Review Queue → Approve → Lock for Audit
    ↓
AuditLog (every field change, before/after)
```

---

## Data Model Design

The core insight is **immutability + audit trail**:

- `RawRecord` — never modified after creation. Stores the original file row as JSON.
- `EmissionRecord` — derived, normalized view. Analyst-editable, but all changes logged.
- `AuditLog` — append-only. Stores before/after values on every field change.
- `Tenant` — every table is scoped by `tenant_id` for multi-tenancy.

Scope classification (1/2/3) is inferred at parse time from material group / energy type / travel segment, and can be overridden by an analyst with audit logging.

---

## Tech Stack

**Backend**
- Django 4.2 + Django REST Framework
- SQLite (dev) / PostgreSQL (prod)
- Pandas — CSV parsing and normalization
- Haversine — great-circle distance from IATA airport codes

**AI Layer**
- LangChain + `langchain-google-genai` — Gemini 2.0 Flash
- LangGraph `StateGraph` — three-node review pipeline
- FAISS + Google Embeddings — RAG store for DEFRA/EPA emission factors
- Rule-based fallback — works without API key

**Frontend**
- React 18 + Vite
- React Router v6
- Recharts — scope breakdown, source comparison, CO₂e charts
- CSS custom properties — no UI framework dependency

**Deployment**
- Backend: Render
- Frontend: Vercel

---

## Project Structure

```
project/
├── manage.py
├── requirement.txt
├── esg_project/          # Django settings, urls, wsgi
├── ingestion/            # Models, parsers, upload views, LLM pipeline
│   ├── models.py         # Tenant, IngestionBatch, RawRecord, EmissionRecord, AuditLog
│   ├── views.py          # SAP / Utility / Travel upload endpoints
│   ├── parsers/
│   │   ├── sap_parser.py
│   │   ├── utility_parser.py
│   │   └── travel_parser.py
│   └── llm/
│       └── review_agent.py   # LangGraph pipeline + Gemini integration
├── analyst/              # Review queue API — list, approve, reject, audit, export
├── sample_data/          # Realistic test files for all three sources
└── frontend/             # React app
    └── src/
        ├── pages/
        │   ├── Dashboard.jsx     # Stats cards + Recharts visualizations
        │   ├── UploadPage.jsx    # Drag-and-drop upload per source
        │   └── ReviewQueue.jsx   # Analyst review table + detail modal
        └── api/
            └── client.js
```

---

## Running Locally

**Prerequisites:** Python 3.11+, Node 18+

```bash
# 1. Clone and create virtual environment
git clone https://github.com/your-username/breathe-esg.git
cd breathe-esg
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# 2. Install backend dependencies
pip install -r requirement.txt

# 3. Set up environment
cp .env.example .env
# Add your GOOGLE_API_KEY from https://aistudio.google.com/app/apikey

# 4. Run migrations and start Django
python manage.py migrate
python manage.py runserver

# 5. In a second terminal — start React
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`

---

## Sample Data

Three realistic test files are in `sample_data/`:

| File | Records | Notable edge cases |
|---|---|---|
| `sap_mb51_sample.csv` | 12 | German headers, DD.MM.YYYY dates, M3/L/KG units |
| `utility_sample.csv` | 10 | Mid-month billing period (Jan 17 – Feb 18), MWh + kWh + therms |
| `travel_sample.json` | 17 | IATA distance calc, multi-leg trips, hotel nights, ground transport |

Upload them from the **Upload Data** page to see the app in action.

---

## Key Decisions

**Why SAP flat file?** SAP can export via IDoc, OData, or flat file. Flat file (ME2M/MB51 transaction export) is what a sustainability team actually emails you — no SAP Basis team or API setup required.

**Why utility portal CSV?** PDFs are fragile to parse (layout changes every redesign). Portal CSV is the realistic path for commercial accounts.

**Why travel JSON?** Concur and Navan both expose REST APIs returning JSON with trip segments. JSON preserves nested segment hierarchy that CSV flattens.

**Why immutable RawRecord?** So analysts can always re-derive or re-parse. If a parser bug is fixed, you can re-process without losing originals.

**What was deliberately not built:**
1. Real-time SAP OData integration — needs a live SAP system and RFC connection
2. PDF bill parsing for utilities — too fragile for a prototype
3. User authentication and role-based access — scoped out to focus on data model quality

---

## Grading Criteria Addressed

| Criterion | Weight | How addressed |
|---|---|---|
| Data model quality | 35% | Immutable RawRecord, full AuditLog, multi-tenancy, Scope 1/2/3 |
| Realistic source handling | 20% | German SAP headers, billing period misalignment, IATA+Haversine |
| Analyst UX | 10% | Review queue, filters, approve/reject, audit trail, CSV/JSON export |
| What was not built | 10% | Three deliberate omissions documented above |

---
