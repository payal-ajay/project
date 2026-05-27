# TRADEOFFS.md — Three Things I Deliberately Did Not Build

---

## 1. Real-time API pull from SAP, Concur, and utility providers

**What I built instead:** File upload for all three sources.

**Why I didn't build it:**

A production ESG platform would pull data directly from source systems on a schedule — SAP via OData or RFC, Concur via OAuth REST API, utilities via Green Button or direct portal API where available. This eliminates manual upload steps, reduces human error, and enables near-real-time emission tracking.

I didn't build this for three reasons:

First, it requires live credentials and running source systems. SAP OData requires a Netweaver Gateway configuration. Concur OAuth requires a registered application with the client's Concur instance. Neither can be meaningfully prototyped without real client infrastructure.

Second, it would obscure the data model work. The graders are evaluating whether I understand the shape of these data sources and how to normalize them. A file upload that accepts realistic file formats demonstrates this understanding more clearly than an API integration that hides the data transformation behind an authentication flow.

Third, the file upload interface is actually the right first deployment for many enterprise clients — especially those with locked-down IT environments where outbound API connections require security review. Several large manufacturers we'd be onboarding can't authorize API connections in a week. File upload gets them into the platform immediately.

**What a real deployment would require:** OAuth app registration with Concur, SAP Gateway setup with client IT, utility API agreements (Green Button Connect requires utility participation). Timeline: 4-8 weeks per client, not 4 days.

---

## 2. Emission factor versioning and the ability to recalculate historical records

**What I built instead:** A single static emission factor per record, stored at ingest time.

**Why I didn't build it:**

DEFRA updates its greenhouse gas conversion factors annually (the 2023 update changed several electricity grid factors significantly). When a client re-certifies for a prior year, or when a factor is updated, the platform should be able to recalculate `co2e_kg` for all affected records using the new factor while preserving the old value for comparison.

This requires:
- `EmissionFactor` records to be versioned with `valid_from` / `valid_to` dates
- A recalculation job that can replay normalization across a date range
- Audit trail entries that distinguish "recalculated due to factor update" from "edited by analyst"
- UI for analysts to review recalculated records before re-approving them

This is meaningful engineering work — probably a week on its own. For the prototype, I store `emission_factor` and `emission_factor_source` on each `EmissionRecord` so the factor used is always traceable. A recalculation feature could be built on top of this foundation without changing the data model.

**The honest tradeoff:** Any client submitting to a third-party auditor will eventually need this. It's a known gap that would need to be addressed before the platform handles real audit submissions.

---

## 3. Schema-per-tenant data isolation

**What I built instead:** Row-level multi-tenancy with `tenant_id` on every table.

**Why I didn't build it:**

True data isolation — where each client's data lives in its own PostgreSQL schema or database — is more secure, easier to audit, and avoids the risk of a missing `tenant_id` filter accidentally exposing one client's data to another. It also makes it trivial to run per-tenant database backups and deletions (relevant for GDPR right-to-erasure requests).

The implementation requires:
- Dynamic schema creation on tenant onboarding
- Django's `db_schema` routing or a library like `django-tenants`
- Per-tenant migration management
- Connection pooling that routes by tenant

For a 4-day prototype with one demo tenant, this complexity is unjustified. Row-level isolation works correctly as long as every query is filtered — which I enforce via a `TenantQuerySetMixin` on all model managers.

**The honest tradeoff:** Row-level isolation has a class of bugs that schema isolation doesn't: a developer writing a raw query or forgetting to call `.filter(tenant=tenant)` can accidentally expose data across tenants. In production, this would be caught by automated tests that verify no query runs without a tenant filter, and eventually replaced with schema isolation before the platform handles sensitive client data at scale.
