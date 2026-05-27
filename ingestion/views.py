import os
import tempfile
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Tenant, IngestionBatch, RawRecord, EmissionRecord
from .parsers import parse_sap_file, parse_utility_file, parse_travel_json
from .llm.review_agent import run_review_agent


def get_or_create_default_tenant():
    tenant, _ = Tenant.objects.get_or_create(
        slug="default", defaults={"name": "Demo Client"}
    )
    return tenant


def ingest_records(batch, parsed_records):
    for rec in parsed_records:
        raw = RawRecord.objects.create(
            batch=batch, tenant=batch.tenant,
            row_index=rec.get("_row_index", 0),
            raw_data=rec.get("_raw", {}),
            parse_errors=rec.get("parse_errors", []),
        )
        if rec.get("quantity") is not None:
            EmissionRecord.objects.create(
                raw_record=raw, tenant=batch.tenant,
                activity_description=rec.get("activity_description", ""),
                category=rec.get("category", "Unknown"),
                source_type=batch.source_type,
                activity_date=rec.get("activity_date") or timezone.now().date(),
                period_start=rec.get("period_start") or None,
                period_end=rec.get("period_end") or None,
                quantity=rec.get("quantity", 0),
                unit=rec.get("unit", "KG"),
                quantity_co2e_kg=rec.get("quantity_co2e_kg"),
                emission_factor_used=rec.get("emission_factor_used", ""),
                emission_factor_source=rec.get("emission_factor_source", ""),
                scope=rec.get("scope", "SCOPE_3"),
                facility_or_entity=rec.get("facility_or_entity", ""),
                origin_iata=rec.get("origin_iata", ""),
                destination_iata=rec.get("destination_iata", ""),
                distance_km=rec.get("distance_km"),
                transport_mode=rec.get("transport_mode", ""),
                travel_class=rec.get("travel_class", ""),
                is_suspicious=rec.get("is_suspicious", False),
                suspicion_reason=rec.get("suspicion_reason", ""),
            )


class SAPUploadView(APIView):
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=400)
        tenant = get_or_create_default_tenant()
        batch = IngestionBatch.objects.create(
            tenant=tenant, source_type="SAP", original_filename=file.name
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            records, errors = parse_sap_file(tmp_path)
            result = run_review_agent(records)
            ingest_records(batch, result["records"])
            batch.row_count = len(records)
            batch.error_count = len(errors)
            batch.llm_summary = result["batch_summary"]
            batch.save()
        finally:
            os.unlink(tmp_path)
        return Response({
            "batch_id": str(batch.id),
            "rows_ingested": batch.row_count,
            "errors": batch.error_count,
            "summary": batch.llm_summary,
        })


class UtilityUploadView(APIView):
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=400)
        tenant = get_or_create_default_tenant()
        batch = IngestionBatch.objects.create(
            tenant=tenant, source_type="UTILITY", original_filename=file.name
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            records, errors = parse_utility_file(tmp_path)
            result = run_review_agent(records)
            ingest_records(batch, result["records"])
            batch.row_count = len(records)
            batch.error_count = len(errors)
            batch.llm_summary = result["batch_summary"]
            batch.save()
        finally:
            os.unlink(tmp_path)
        return Response({
            "batch_id": str(batch.id),
            "rows_ingested": batch.row_count,
            "errors": batch.error_count,
            "summary": batch.llm_summary,
        })


class TravelUploadView(APIView):
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=400)
        tenant = get_or_create_default_tenant()
        batch = IngestionBatch.objects.create(
            tenant=tenant, source_type="TRAVEL", original_filename=file.name
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            records, errors = parse_travel_json(tmp_path)
            result = run_review_agent(records)
            ingest_records(batch, result["records"])
            batch.row_count = len(records)
            batch.error_count = len(errors)
            batch.llm_summary = result["batch_summary"]
            batch.save()
        finally:
            os.unlink(tmp_path)
        return Response({
            "batch_id": str(batch.id),
            "rows_ingested": batch.row_count,
            "errors": batch.error_count,
            "summary": batch.llm_summary,
        })