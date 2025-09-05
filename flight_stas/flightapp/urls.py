# flightapp/urls.py
from django.urls import path
from .views import  FlightStatisticsSQL, FlightStatisticsAPIView, FlightStatisticsAPIView2, FlightStatisticsAPIView4
urlpatterns = [
   
    path('stats1/', FlightStatisticsSQL.as_view()),
    path('stats2/', FlightStatisticsAPIView.as_view()),
    path('stats3/', FlightStatisticsAPIView2.as_view()),
    path('stats4/', FlightStatisticsAPIView4.as_view()),

]
