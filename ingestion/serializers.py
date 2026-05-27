from rest_framework import serializers
from .models import EmissionRecord, Tenant, AuditLog


class EmissionRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'activity_description', 'category', 'source_type', 'activity_date',
            'period_start', 'period_end', 'quantity', 'unit', 'quantity_co2e_kg',
            'emission_factor_used', 'emission_factor_source', 'scope', 'facility_or_entity',
            'country_code', 'origin_iata', 'destination_iata', 'distance_km', 'transport_mode',
            'travel_class', 'status', 'is_locked', 'is_suspicious', 'suspicion_reason',
            'reviewed_by', 'reviewed_at', 'created_at', 'updated_at'
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'field_name', 'old_value', 'new_value', 'changed_at', 'change_reason']
