from django.urls import path
from .views import ConvertVideo

urlpatterns = [
     path('convert/', ConvertVideo.as_view(), name='convert'),
]
