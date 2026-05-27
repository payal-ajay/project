from django.urls import path
from .views import (
    EmissionListView, EmissionDetailView,
    ApproveView, RejectView, AuditLogView,
    ExportCSVView, ExportJSONView,
)

urlpatterns = [
    path("emissions/", EmissionListView.as_view()),
    path("emissions/<uuid:pk>/", EmissionDetailView.as_view()),
    path("emissions/<uuid:pk>/approve/", ApproveView.as_view()),
    path("emissions/<uuid:pk>/reject/", RejectView.as_view()),
    path("emissions/<uuid:pk>/audit/", AuditLogView.as_view()),
    path("export/csv/", ExportCSVView.as_view()),
    path("export/json/", ExportJSONView.as_view()),
]