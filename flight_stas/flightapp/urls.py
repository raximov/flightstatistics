# flightapp/urls.py
from django.urls import path
from .views import  FlightStatisticsSQL, FlightStatisticsAPIView, FlightStatisticsAPIView2
urlpatterns = [
   
    path('stats1/', FlightStatisticsSQL.as_view()),
    path('stats2/', FlightStatisticsAPIView.as_view()),
    path('stats3/', FlightStatisticsAPIView2.as_view()),

]
