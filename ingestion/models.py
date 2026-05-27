from django.db import models
from django.contrib.auth.models import User
import uuid


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class IngestionBatch(models.Model):
    SOURCE_TYPES = [
        ("SAP", "SAP Flat File"),
        ("UTILITY", "Utility Portal CSV"),
        ("TRAVEL", "Corporate Travel JSON"),
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
    llm_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.source_type} — {self.original_filename}"


class RawRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="raw_records")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    row_index = models.IntegerField()
    raw_data = models.JSONField()
    parse_errors = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["batch", "row_index"]
        unique_together = [("batch", "row_index")]

    def __str__(self):
        return f"Raw #{self.row_index} — Batch {self.batch_id}"


class EmissionRecord(models.Model):
    SCOPE_CHOICES = [
        ("SCOPE_1", "Scope 1 — Direct emissions"),
        ("SCOPE_2", "Scope 2 — Purchased electricity"),
        ("SCOPE_3", "Scope 3 — Value chain"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("FLAGGED", "Flagged"),
    ]
    UNIT_CHOICES = [
        ("KWH", "kWh"), ("MWH", "MWh"), ("LITER", "Liter"),
        ("KG", "Kilogram"), ("TONNE", "Metric Tonne"),
        ("KM", "Kilometer"), ("THERM", "Therm"),
        ("MMBTU", "MMBtu"), ("NIGHT", "Night"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_record = models.OneToOneField(RawRecord, on_delete=models.CASCADE, related_name="emission")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="emissions")

    activity_description = models.CharField(max_length=500)
    category = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20)

    activity_date = models.DateField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    quantity_co2e_kg = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    emission_factor_used = models.CharField(max_length=500, blank=True)
    emission_factor_source = models.CharField(max_length=200, blank=True)

    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    facility_or_entity = models.CharField(max_length=300, blank=True)
    country_code = models.CharField(max_length=3, blank=True)

    origin_iata = models.CharField(max_length=3, blank=True)
    destination_iata = models.CharField(max_length=3, blank=True)
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    transport_mode = models.CharField(max_length=50, blank=True)
    travel_class = models.CharField(max_length=50, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    is_locked = models.BooleanField(default=False)
    is_suspicious = models.BooleanField(default=False)
    suspicion_reason = models.TextField(blank=True)
    llm_flag_note = models.TextField(blank=True)

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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    emission_record = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name="audit_logs")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    change_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.field_name}: {self.old_value} → {self.new_value}"


class EmissionFactor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=200)
    subcategory = models.CharField(max_length=200, blank=True)
    unit = models.CharField(max_length=50)
    co2e_per_unit = models.DecimalField(max_digits=12, decimal_places=6)
    source = models.CharField(max_length=200)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    scope = models.CharField(max_length=20)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.category} — {self.co2e_per_unit} kgCO2e/{self.unit}"