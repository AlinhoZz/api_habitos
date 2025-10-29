from django.urls import path
from .views import healthz

urlpatterns = [
    path("healthz/", healthz),
]
