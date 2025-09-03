# flightapp/urls.py
from django.urls import path
from .views import FlightStatistics1,FlightStatistics2, FlightStatisticsAPIView3, FlightStatisticsSQL4
urlpatterns = [
    path('stats1/', FlightStatistics1.as_view(), name='flight_statistics1'), 
    path('stats2/', FlightStatistics2.as_view(), name='flight_statistics2'), 
    path('stats3/', FlightStatisticsAPIView3.as_view()  ),
    path('stats4/', FlightStatisticsSQL4.as_view())
]
