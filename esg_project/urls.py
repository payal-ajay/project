from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def health_check(request):
    """Health check endpoint"""
    return JsonResponse({
        'status': 'ok',
        'message': 'Breathe ESG API is running',
        'endpoints': {
            'admin': '/admin/',
            'api_ingestion': '/api/ingestion/',
            'api_analyst': '/api/analyst/',
        }
    })

urlpatterns = [
    path('', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('api/ingestion/', include('ingestion.urls')),
    path('api/analyst/', include('analyst.urls')),
]