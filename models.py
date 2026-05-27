"""
models.py — Ingestion app

Data model design decisions:
- RawRecord is immutable. Once created, never updated. Stores the original row exactly.
- EmissionRecord is the normalized, derived view. Analyst-editable, but all edits are logged.
- Multi-tenancy is row-level via tenant_id on every table.
- AuditLog captures before/after on every edit — not just the final value.
- Scope (1/2/3) is inferred at parse time but analyst can override (with audit log).
"""

from django.db import models
from django.contrib.auth.models import User
import uuid


class Tenant(models.Model):
    """
    Multi-tenancy unit. Every record is scoped to a tenant.
    In production, users would belong to tenants via a membership table.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class IngestionBatch(models.Model):
    """
    One file upload = one batch. Tracks provenance at the file level.
    If an analyst needs to re-ingest a file, a new batch is created — old one stays.
    """
    SOURCE_TYPES = [
        ("SAP", "SAP Flat File (Fuel/Procurement)"),
        ("UTILITY", "Utility Portal CSV (Electricity)"),
        ("TRAVEL", "Corporate Travel JSON (Concur/Navan)"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending Review"),
        ("PARTIAL", "Partially Approved"),
        ("APPROVED", "Fully Approved"),
        ("REJECTED", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="batches")
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    original_filename = models.CharField(max_length=500)
    uploaded_file = models.FileField(upload_to="raw_uploads/%Y/%m/", null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    row_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    llm_summary = models.TextField(blank=True)  # LangGraph analysis summary

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.source_type} — {self.original_filename} ({self.uploaded_at.date()})"


class RawRecord(models.Model):
    """
    Immutable source-of-truth. Never written to after creation.
    Stores the original row as-is so we can always re-derive or re-parse.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="raw_records")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    row_index = models.IntegerField()           # Original row number in the file
    raw_data = models.JSONField()               # Full original row, key-value as parsed
    parse_errors = models.JSONField(default=list)  # List of parse warnings/errors
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["batch", "row_index"]
        unique_together = [("batch", "row_index")]

    def __str__(self):
        return f"Raw #{self.row_index} — Batch {self.batch_id}"


class EmissionRecord(models.Model):
    """
    Normalized, analyst-facing record. Derived from RawRecord.
    Analyst can edit quantity, unit, scope — all edits logged in AuditLog.
    Once approved, locked (is_locked=True). Locked records go to auditors.
    """
    SCOPE_CHOICES = [
        ("SCOPE_1", "Scope 1 — Direct emissions"),
        ("SCOPE_2", "Scope 2 — Purchased electricity/heat"),
        ("SCOPE_3", "Scope 3 — Value chain"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("FLAGGED", "Flagged for Review"),
    ]
    UNIT_CHOICES = [
        ("KWH", "kWh"),
        ("MWH", "MWh"),
        ("LITER", "Liter"),
        ("KG", "Kilogram"),
        ("TONNE", "Metric Tonne"),
        ("KM", "Kilometer"),
        ("THERM", "Therm"),
        ("MMBTU", "MMBtu"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_record = models.OneToOneField(RawRecord, on_delete=models.CASCADE, related_name="emission")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="emissions")

    # --- What happened ---
    activity_description = models.CharField(max_length=500)
    category = models.CharField(max_length=200)   # e.g. "Natural Gas", "Electricity", "Air Travel"
    source_type = models.CharField(max_length=20)  # SAP / UTILITY / TRAVEL

    # --- When ---
    activity_date = models.DateField()
    period_start = models.DateField(null=True, blank=True)  # For utility billing periods
    period_end = models.DateField(null=True, blank=True)

    # --- Quantity (normalized) ---
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    quantity_co2e_kg = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    emission_factor_used = models.CharField(max_length=500, blank=True)  # Source of factor
    emission_factor_source = models.CharField(max_length=200, blank=True)  # e.g. "DEFRA 2023"

    # --- Scope ---
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)

    # --- Location / entity ---
    facility_or_entity = models.CharField(max_length=300, blank=True)
    country_code = models.CharField(max_length=3, blank=True)

    # --- Travel-specific ---
    origin_iata = models.CharField(max_length=3, blank=True)
    destination_iata = models.CharField(max_length=3, blank=True)
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    transport_mode = models.CharField(max_length=50, blank=True)
    travel_class = models.CharField(max_length=50, blank=True)

    # --- Review workflow ---
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    is_locked = models.BooleanField(default=False)
    is_suspicious = models.BooleanField(default=False)
    suspicion_reason = models.TextField(blank=True)
    llm_flag_note = models.TextField(blank=True)  # LangGraph anomaly note

    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_emissions"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activity_date"]

    def __str__(self):
        return f"{self.category} — {self.quantity} {self.unit} ({self.activity_date})"


class AuditLog(models.Model):
    """
    Append-only audit trail. Every field change on EmissionRecord is logged here.
    Before/after stored so you can reconstruct state at any point in time.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    emission_record = models.ForeignKey(
        EmissionRecord, on_delete=models.CASCADE, related_name="audit_logs"
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    change_reason = models.TextField(blank=True)  # Analyst can provide reason

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.field_name}: {self.old_value} → {self.new_value} at {self.changed_at}"


class EmissionFactor(models.Model):
    """
    Lookup table for CO2e factors.
    Populated from DEFRA/IPCC docs (or via RAG retrieval in the LangChain layer).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=200)
    subcategory = models.CharField(max_length=200, blank=True)
    unit = models.CharField(max_length=50)
    co2e_per_unit = models.DecimalField(max_digits=12, decimal_places=6)
    source = models.CharField(max_length=200)  # "DEFRA 2023", "IPCC AR6", etc.
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    scope = models.CharField(max_length=20)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.category} / {self.subcategory} — {self.co2e_per_unit} kgCO2e/{self.unit}"