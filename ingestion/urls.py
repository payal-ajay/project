from django.urls import path
from .views import SAPUploadView, UtilityUploadView, TravelUploadView

urlpatterns = [
    path("upload/sap/", SAPUploadView.as_view()),
    path("upload/utility/", UtilityUploadView.as_view()),
    path("upload/travel/", TravelUploadView.as_view()),
]