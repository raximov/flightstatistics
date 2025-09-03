from datetime import timedelta
from math import radians, cos, sin, acos
import math
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse
from rest_framework import status
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField, Q
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import connection
from datetime import datetime
import json
import ast


from .models import AirportsData, Flights, TicketFlights


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



class FlightStatisticsAPIView3(APIView):
    def get(self, request, *args, **kwargs):
        departure_airport_name = request.GET.get('departure_airport')
        from_date_str = request.GET.get('from_date')
        to_date_str = request.GET.get('to_date')


        dep_airport = AirportsData.objects.filter(
            airport_name__en=departure_airport_name
        ).first()
        
        if not dep_airport:
            return Response({'error': 'Airport not found'}, status=404)


        from_date = timezone.datetime.fromisoformat(from_date_str)
        to_date = timezone.datetime.fromisoformat(to_date_str) + timedelta(days=1)


        dep_coords = ast.literal_eval(dep_airport.coordinates)
        dep_lon, dep_lat = dep_coords
        dep_lat_rad = math.radians(dep_lat)
        dep_lon_rad = math.radians(dep_lon)

        all_flights = Flights.objects.filter(
            departure_airport=dep_airport,
            scheduled_departure__gte=from_date,
            scheduled_departure__lt=to_date
        ).values('arrival_airport').annotate(
            flight_ids=ArrayAgg('flight_id'),
            flight_count=Count('flight_id')
        ).order_by('arrival_airport')

        completed_flights_avg = Flights.objects.filter(
            departure_airport=dep_airport,
            scheduled_departure__gte=from_date,
            scheduled_departure__lt=to_date,
            actual_departure__isnull=False,
            actual_arrival__isnull=False
        ).values('arrival_airport').annotate(
            avg_flight_time=Avg(
                ExpressionWrapper(
                    F('actual_arrival') - F('actual_departure'),
                    output_field=DurationField()
                )
            )
        )

        avg_time_map = {item['arrival_airport']: item['avg_flight_time'] for item in completed_flights_avg}

        arrival_airport_codes = [stat['arrival_airport'] for stat in all_flights]
        arrival_airports = AirportsData.objects.filter(
            airport_code__in=arrival_airport_codes
        )
        arrival_airport_map = {airport.airport_code: airport for airport in arrival_airports}

        all_flight_ids = []
        for stat in all_flights:
            all_flight_ids.extend(stat['flight_ids'])
        
        passenger_counts = TicketFlights.objects.filter(
            flight_id__in=all_flight_ids
        ).values('flight_id').annotate(
            passenger_count=Count('flight_id')
        )
        
        flight_passenger_map = {pc['flight_id']: pc['passenger_count'] for pc in passenger_counts}

        results = []
        for stat in all_flights:
            arrival_airport_code = stat['arrival_airport']
            arrival_airport = arrival_airport_map.get(arrival_airport_code)
            
            if not arrival_airport:
                continue

            passenger_count = sum(
                flight_passenger_map.get(flight_id, 0) 
                for flight_id in stat['flight_ids']
            )

            arr_coords = ast.literal_eval(arrival_airport.coordinates)
            arr_lon, arr_lat = arr_coords
            arr_lat_rad = math.radians(arr_lat)
            arr_lon_rad = math.radians(arr_lon)
            
            try:
                distance_km = 6371 * math.acos(
                    math.cos(dep_lat_rad) * math.cos(arr_lat_rad) *
                    math.cos(arr_lon_rad - dep_lon_rad) +
                    math.sin(dep_lat_rad) * math.sin(arr_lat_rad)
                )
            except ValueError:
                distance_km = 0

            avg_flight_time = avg_time_map.get(arrival_airport_code)
            avg_time_str = None
            if avg_flight_time:
                total_seconds = avg_flight_time.total_seconds()
                avg_time_str = str(timedelta(seconds=int(total_seconds)))

            results.append({
                'arrival_airport': arrival_airport_code,
                'airport_name': arrival_airport.airport_name.get('en', ''),
                # 'flight_ids': stat['flight_ids'],
                'avg_flight_time': avg_time_str,
                'flight_count': stat['flight_count'],
                'passenger_count': passenger_count, 
                'distance_km': round(distance_km, 3)
            })

        results.sort(key=lambda x: x['distance_km'])
        
        return Response(results)
        



class FlightStatisticsSQL4(APIView):
    def get(self, request):

        departure_airport = request.GET.get('departure_airport')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        
        query = """
        WITH depcity AS (
            SELECT airport_code,  
                   RADIANS(a.coordinates[1])::float8 AS dep_lat,
                   RADIANS(a.coordinates[0])::float8 AS dep_lon
            FROM bookings.airports_data a
            WHERE airport_name ->> 'en' = %s
        ),
        filtered_flights AS (
            SELECT f.*
            FROM bookings.flights f
            JOIN depcity d ON f.departure_airport = d.airport_code
            WHERE f.scheduled_departure >= %s
              AND f.scheduled_departure < %s
        ),
        flights_list AS (
            SELECT 
                arrival_airport,
                ARRAY_AGG(flight_id) AS flight_ids,  
                AVG(actual_arrival - actual_departure) AS avg_flight_time,
                COUNT(flight_id) AS flight_count
            FROM filtered_flights
            GROUP BY arrival_airport
        )
        SELECT 
            ad.airport_name ->> 'en' AS airport_name,
            ROUND(
              6371 * ACOS(
                  COS(d.dep_lat) * COS(RADIANS(ad.coordinates[1])) *
                  COS(RADIANS(ad.coordinates[0]) - d.dep_lon) +
                  SIN(d.dep_lat) * SIN(RADIANS(ad.coordinates[1]))
              )::numeric, 3
            ) AS distance_km,
            fl.avg_flight_time,
            fl.flight_count,
            (
                SELECT COUNT(*) 
                FROM bookings.ticket_flights tf
                WHERE tf.flight_id = ANY(fl.flight_ids)
            ) AS passenger_count
        FROM flights_list fl
        JOIN bookings.airports_data ad
          ON ad.airport_code = fl.arrival_airport
        CROSS JOIN depcity d   
        ORDER BY distance_km ASC;
        """
        
        try:
            with connection.cursor() as cursor:

                cursor.execute(query, [departure_airport, from_date, to_date])
                results = cursor.fetchall()
                

                flights_data = []
                for row in results:
                    flights_data.append({
                        'airport_name': row[0],
                        'distance_km': float(row[1]) if row[1] else None,
                        'avg_flight_time': str(row[2]) if row[2] else None,
                        'flight_count': row[3],
                        'passenger_count': row[4]
                    })
                
                return JsonResponse({
                    
                    'data': flights_data,
                })
                
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e),
                'parameters': {
                    'departure_airport': departure_airport,
                    'from_date': from_date,
                    'to_date': to_date
                }
            }, status=500)
