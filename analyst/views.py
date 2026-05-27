import csv
import json
from django.utils import timezone
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from ingestion.models import EmissionRecord, AuditLog


def serialize_emission(e):
    return {
        "id": str(e.id),
        "category": e.category,
        "scope": e.scope,
        "source_type": e.source_type,
        "activity_date": str(e.activity_date),
        "period_start": str(e.period_start) if e.period_start else None,
        "period_end": str(e.period_end) if e.period_end else None,
        "quantity": float(e.quantity),
        "unit": e.unit,
        "quantity_co2e_kg": float(e.quantity_co2e_kg) if e.quantity_co2e_kg else None,
        "emission_factor_used": e.emission_factor_used,
        "emission_factor_source": e.emission_factor_source,
        "facility_or_entity": e.facility_or_entity,
        "origin_iata": e.origin_iata,
        "destination_iata": e.destination_iata,
        "distance_km": float(e.distance_km) if e.distance_km else None,
        "transport_mode": e.transport_mode,
        "travel_class": e.travel_class,
        "activity_description": e.activity_description,
        "status": e.status,
        "is_suspicious": e.is_suspicious,
        "suspicion_reason": e.suspicion_reason,
        "is_locked": e.is_locked,
        "batch_id": str(e.raw_record.batch_id),
        "created_at": e.created_at.isoformat(),
    }


class EmissionListView(APIView):
    def get(self, request):
        qs = EmissionRecord.objects.select_related("raw_record__batch").all()
        if s := request.query_params.get("status"):
            qs = qs.filter(status=s.upper())
        if s := request.query_params.get("scope"):
            qs = qs.filter(scope=s.upper())
        if s := request.query_params.get("source_type"):
            qs = qs.filter(source_type=s.upper())
        if s := request.query_params.get("suspicious"):
            qs = qs.filter(is_suspicious=s.lower() == "true")
        data = [serialize_emission(e) for e in qs[:200]]
        return Response({"count": len(data), "results": data})


class EmissionDetailView(APIView):
    def get(self, request, pk):
        try:
            return Response(serialize_emission(EmissionRecord.objects.get(pk=pk)))
        except EmissionRecord.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

    def patch(self, request, pk):
        try:
            e = EmissionRecord.objects.get(pk=pk)
        except EmissionRecord.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        if e.is_locked:
            return Response({"error": "Record is locked — already approved for audit"}, status=400)
        for field in ["quantity", "unit", "scope", "category", "activity_description"]:
            if field in request.data:
                old = str(getattr(e, field))
                new = str(request.data[field])
                if old != new:
                    AuditLog.objects.create(
                        emission_record=e, tenant=e.tenant,
                        changed_by=request.user if request.user.is_authenticated else None,
                        field_name=field, old_value=old, new_value=new,
                        change_reason=request.data.get("change_reason", ""),
                    )
                    setattr(e, field, request.data[field])
        e.save()
        return Response(serialize_emission(e))


class ApproveView(APIView):
    def post(self, request, pk):
        try:
            e = EmissionRecord.objects.get(pk=pk)
        except EmissionRecord.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        AuditLog.objects.create(
            emission_record=e, tenant=e.tenant,
            changed_by=request.user if request.user.is_authenticated else None,
            field_name="status", old_value=e.status, new_value="APPROVED",
        )
        e.status = "APPROVED"
        e.is_locked = True
        e.reviewed_at = timezone.now()
        e.save()
        return Response({"status": "approved", "id": str(e.id)})


class RejectView(APIView):
    def post(self, request, pk):
        try:
            e = EmissionRecord.objects.get(pk=pk)
        except EmissionRecord.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        reason = request.data.get("reason", "")
        AuditLog.objects.create(
            emission_record=e, tenant=e.tenant,
            changed_by=request.user if request.user.is_authenticated else None,
            field_name="status", old_value=e.status, new_value="REJECTED",
            change_reason=reason,
        )
        e.status = "REJECTED"
        e.reviewed_at = timezone.now()
        e.save()
        return Response({"status": "rejected", "id": str(e.id)})


class AuditLogView(APIView):
    def get(self, request, pk):
        try:
            e = EmissionRecord.objects.get(pk=pk)
        except EmissionRecord.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        return Response({"record_id": str(pk), "audit_trail": [
            {
                "changed_at": log.changed_at.isoformat(),
                "field": log.field_name,
                "old_value": log.old_value,
                "new_value": log.new_value,
                "reason": log.change_reason,
            }
            for log in e.audit_logs.all()
        ]})


class ExportCSVView(APIView):
    def get(self, request):
        qs = EmissionRecord.objects.select_related("raw_record__batch").all()
        if s := request.query_params.get("status"):
            qs = qs.filter(status=s.upper())
        if s := request.query_params.get("source_type"):
            qs = qs.filter(source_type=s.upper())

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="emissions_export.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "id", "category", "scope", "source_type",
            "activity_date", "period_start", "period_end",
            "quantity", "unit", "quantity_co2e_kg",
            "emission_factor_used", "emission_factor_source",
            "facility_or_entity", "origin_iata", "destination_iata",
            "distance_km", "transport_mode", "travel_class",
            "activity_description", "status", "is_suspicious",
            "suspicion_reason", "batch_id",
        ])
        for e in qs:
            writer.writerow([
                str(e.id), e.category, e.scope, e.source_type,
                e.activity_date, e.period_start, e.period_end,
                e.quantity, e.unit, e.quantity_co2e_kg,
                e.emission_factor_used, e.emission_factor_source,
                e.facility_or_entity, e.origin_iata, e.destination_iata,
                e.distance_km, e.transport_mode, e.travel_class,
                e.activity_description, e.status, e.is_suspicious,
                e.suspicion_reason, str(e.raw_record.batch_id),
            ])
        return response


class ExportJSONView(APIView):
    def get(self, request):
        qs = EmissionRecord.objects.select_related("raw_record__batch").all()
        if s := request.query_params.get("status"):
            qs = qs.filter(status=s.upper())
        if s := request.query_params.get("source_type"):
            qs = qs.filter(source_type=s.upper())

        data = [serialize_emission(e) for e in qs[:500]]
        response = HttpResponse(
            json.dumps({"count": len(data), "exported_at": timezone.now().isoformat(), "records": data}, indent=2),
            content_type="application/json"
        )
        response["Content-Disposition"] = 'attachment; filename="emissions_export.json"'
        return response