# flightapp/urls.py
from django.urls import path
from .views import FlightStatistics1,FlightStatistics2, FlightStatisticsAPIView3
urlpatterns = [
    path('stats1/', FlightStatistics1.as_view(), name='flight_statistics'), 
    path('stats2/', FlightStatistics2.as_view(), name='flight_statistics'), 
    path('stats3/', FlightStatisticsAPIView3.as_view()  ),
]