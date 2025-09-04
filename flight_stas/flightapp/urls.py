# flightapp/urls.py
from django.urls import path
from .views import  FlightStatisticsSQL, FlightStatisticsAPIView
urlpatterns = [
   
    path('stats1/', FlightStatisticsSQL.as_view()),
    path('stats2/', FlightStatisticsAPIView.as_view())
]
