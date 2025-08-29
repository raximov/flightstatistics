from datetime import timedelta
from math import radians, cos, sin, acos
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, F, Avg, ExpressionWrapper, DurationField
from django.db import connection

import ast

from .models import Flights, AirportsData


def haversine_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    return 6371 * acos(
        cos(lat1) * cos(lat2) * cos(lon2 - lon1) + sin(lat1) * sin(lat2)
    )


class FlightStatistics1(APIView):
    def get(self, request, *args, **kwargs):
        airport_code = request.GET.get('departure_airport')
        from_date_str = request.GET.get('from_date')
        to_date_str = request.GET.get('to_date')

        if not airport_code:
            return Response({'error': 'departure_airport kiriting.'}, status=400)
        if not from_date_str or not to_date_str:
            return Response({'error': 'from_date va to_date kerak.'}, status=400)

        departure_airport = get_object_or_404(AirportsData, airport_code=airport_code)

        try:
            from_date = timezone.datetime.fromisoformat(from_date_str)
            to_date = timezone.datetime.fromisoformat(to_date_str) + timedelta(days=1)
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

        duration_expr = ExpressionWrapper(
            F('actual_arrival') - F('actual_departure'),
            output_field=DurationField()
        )

        flights_stats = (
            Flights.objects.filter(
                departure_airport=departure_airport,
                scheduled_departure__gte=from_date,
                scheduled_departure__lt=to_date
            )
            .select_related('arrival_airport')
            .annotate(
                passengers_count=Count('ticketflights__ticket_no', distinct=True),
                flight_duration=duration_expr
            )
        )

        stats = {}
        dep_lon, dep_lat = ast.literal_eval(departure_airport.coordinates)

        for flight in flights_stats:
            arr_airport = flight.arrival_airport
            key = arr_airport.airport_code
            arr_lon, arr_lat = ast.literal_eval(arr_airport.coordinates)
            distance = haversine_distance(dep_lat, dep_lon, arr_lat, arr_lon)

            if key not in stats:
                stats[key] = {
                    'airport_name': arr_airport.airport_name.get('en', key),
                    'flight_count': 0,
                    'passengers_count': 0,
                    'distance_km': round(distance, 3),
                    'durations': []
                }

            stats[key]['flight_count'] += 1
            stats[key]['passengers_count'] += flight.passengers_count
            if flight.flight_duration:
                stats[key]['durations'].append(flight.flight_duration.total_seconds())

        for val in stats.values():
            if val['durations']:
                avg_sec = sum(val['durations']) / len(val['durations'])
                hours = int(avg_sec // 3600)
                minutes = int((avg_sec % 3600) // 60)
                seconds = int(avg_sec % 60)
                val['avg_duration'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                val['avg_duration'] = "00:00:00"
            del val['durations']

        arrival_stats_sorted = sorted(stats.values(), key=lambda x: x['distance_km'])

        return Response({
            'departure_airport': departure_airport.airport_code,
            'arrival_stats': arrival_stats_sorted
        }, status=200)




class FlightStatistics2(APIView):
    def get(self, request, *args, **kwargs):
        airport_code = request.GET.get('departure_airport')
        from_date_str = request.GET.get('from_date')
        to_date_str = request.GET.get('to_date')

        if not airport_code:
            return Response({'error': 'departure_airport kiriting.'}, status=400)
        if not from_date_str or not to_date_str:
            return Response({'error': 'from_date and to_date are required.'}, status=400)

        departure_airport = get_object_or_404(AirportsData, airport_code=airport_code)

        try:
            from_date = timezone.datetime.fromisoformat(from_date_str)
            to_date = timezone.datetime.fromisoformat(to_date_str) + timedelta(days=1)
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

        sql = """
        WITH flights_extended AS (
            SELECT f.flight_id, f.arrival_airport, f.departure_airport,
                   f.actual_arrival, f.actual_departure,
                   tf.ticket_no,
                   fdep.airport_name AS dep_name,
                   farr.airport_name AS arr_name,
                   (fdep.coordinates[0])::float AS dep_lon,
                   (fdep.coordinates[1])::float AS dep_lat,
                   (farr.coordinates[0])::float AS arr_lon,
                   (farr.coordinates[1])::float AS arr_lat
            FROM bookings.flights f
            JOIN bookings.airports_data fdep ON f.departure_airport = fdep.airport_code
            JOIN bookings.airports_data farr ON f.arrival_airport = farr.airport_code
            LEFT JOIN bookings.ticket_flights tf ON f.flight_id = tf.flight_id
            WHERE f.departure_airport = %s
              AND f.scheduled_departure >= %s
              AND f.scheduled_departure < %s
        ),
        arrival_stats AS (
            SELECT 
                arr_name ->> 'en' AS airport_name,
                ROUND(
                    6371 * ACOS(
                        COS(RADIANS(dep_lat)) * COS(RADIANS(arr_lat)) *
                        COS(RADIANS(arr_lon) - RADIANS(dep_lon)) +
                        SIN(RADIANS(dep_lat)) * SIN(RADIANS(arr_lat))
                    )::numeric, 3
                ) AS distance_km,
                COUNT(DISTINCT flight_id) AS flight_count,
                COUNT(ticket_no) AS passengers_count,
                TO_CHAR(AVG(actual_arrival - actual_departure), 'HH24:MI:SS') AS avg_duration
            FROM flights_extended
            GROUP BY arr_name, dep_lat, dep_lon, arr_lat, arr_lon
        )
        SELECT *
        FROM arrival_stats
        ORDER BY distance_km ASC
        LIMIT 100;
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, [airport_code, from_date, to_date])
            columns = [col[0] for col in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not results:
            return Response({'message': 'No flights found for the given criteria.'}, status=404)

        return Response({
            'departure_airport': departure_airport.airport_code,
            'arrival_stats': results
        }, status=200)
