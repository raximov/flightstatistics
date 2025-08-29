from rest_framework import serializers
from .models import AirportsData

class AirportStatsSerializer(serializers.Serializer):
    arrival_airport = serializers.CharField()
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    distance_km = serializers.FloatField()
    passengers_count = serializers.IntegerField()
    flights_count = serializers.IntegerField()
    average_flight_time = serializers.DurationField()

