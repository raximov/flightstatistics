from datetime import timedelta
import math
from math import radians, sin ,cos , acos
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse
from rest_framework import status
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField, FloatField
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import connection
import ast
# from django.contrib.gis.db.models.functions import Distance
        

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
    def get(self, request):
        departure_airport_name = request.GET.get('departure_airport_name')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        
        if not departure_airport_name:
            return Response({
                'status': 'error',
                'message': 'Missing required parameter: departure_airport_name'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not from_date or not to_date:
            return Response({
                'status': 'error',
                'message': 'Missing required parameters: from_date and to_date'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            from .models import AirportsData, Flights, TicketFlights
            
            # Get departure airport
            dep_airport = AirportsData.objects.get(airport_name__en=departure_airport_name)
            
            # Use PostGIS ST_DistanceSphere function
            from django.db.models.expressions import RawSQL
            
            # Calculate distance in kilometers using ST_DistanceSphere
            distance_sql = """
                ST_DistanceSphere(
                    ST_MakePoint(%s, %s),
                    ST_MakePoint(
                    ST_X(coordinates),
                    ST_Y(coordinates)
                    )
                ) / 1000.0
            """ % (dep_airport.coordinates.x, dep_airport.coordinates.y)
            
            # Main query using pure Django ORM with PostGIS
            results = AirportsData.objects.filter(
                arriving_flights__departure_airport=dep_airport,
                arriving_flights__scheduled_departure__gte=from_date,
                arriving_flights__scheduled_departure__lt=to_date
            ).annotate(
                distance_km=RawSQL(distance_sql, (), output_field=FloatField()),
                avg_flight_time=Avg(
                    F('arriving_flights__actual_arrival') - 
                    F('arriving_flights__actual_departure')
                ),
                flight_count=Count('arriving_flights'),
                passenger_count=Count('arriving_flights__ticketflights__ticket_no')
            ).values(
                'airport_name__en', 
                'distance_km', 
                'avg_flight_time', 
                'flight_count', 
                'passenger_count'
            ).order_by('distance_km')
            
            flights_data = []
            for result in results:
                flights_data.append({
                    'airport_name': result['airport_name__en'],
                    'distance_km': round(result['distance_km'], 3) if result['distance_km'] is not None else None,
                    'avg_flight_time': str(result['avg_flight_time']) if result['avg_flight_time'] is not None else None,
                    'flight_count': result['flight_count'],
                    'passenger_count': result['passenger_count']
                })
            
            return Response({'data': flights_data})
            
        except AirportsData.DoesNotExist:
            return Response({
                'status': 'error',
                'message': f'Airport "{departure_airport_name}" not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e),
                'parameters': {
                    'departure_airport_name': departure_airport_name,
                    'from_date': from_date,
                    'to_date': to_date
                }
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        




class FlightStatisticsSQL4(APIView):
    def get(self, request):
        # Get parameters
        departure_airport_name = request.GET.get('departure_airport_name')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        
        # Validate required parameters
        if not departure_airport_name:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required parameter: departure_airport_name'
            }, status=400)
        
        if not from_date or not to_date:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required parameters: from_date and to_date'
            }, status=400)

        query = """
        WITH depcity AS (
            SELECT airport_code,  
                   RADIANS(ST_Y(a.coordinates))::float8 AS dep_lat,
                   RADIANS(ST_X(a.coordinates))::float8 AS dep_lon
            FROM bookings.airports_data a
            WHERE airport_name ->> 'en' = %s
        ),
        filtered_flights AS (
            SELECT f.*
            FROM bookings.flights f
            JOIN depcity d ON f.departure_airport = d.airport_code
            WHERE f.scheduled_departure >= %s::timestamp
              AND f.scheduled_departure < %s::timestamp
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
                  COS(d.dep_lat) * COS(RADIANS(ST_Y(ad.coordinates))) *
                  COS(RADIANS(ST_X(ad.coordinates)) - d.dep_lon) +
                  SIN(d.dep_lat) * SIN(RADIANS(ST_Y(ad.coordinates)))
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
        
        
        with connection.cursor() as cursor:
            # Execute the query with parameters
            cursor.execute(query, [departure_airport_name, from_date, to_date])
            results = cursor.fetchall()
                
            # Process results
            flights_data = []
            for row in results:
                flights_data.append({
                    'airport_name': row[0],
                    'distance_km': float(row[1]) if row[1] is not None else None,
                    'avg_flight_time': str(row[2]) if row[2] is not None else None,
                    'flight_count': row[3],
                    'passenger_count': row[4]
                })
                
            return JsonResponse({
                'data': flights_data
            })
                
    




class FlightStatisticsAPIView5(APIView):
    def get(self, request):
        departure_airport_name = request.GET.get('departure_airport_name')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')

        
        
        dep_airport = AirportsData.objects.get(airport_name__en=departure_airport_name)

        dep_lat = math.radians(dep_airport.coordinates.y)
        dep_lon = math.radians(dep_airport.coordinates.x)
        filtered_flights = Flights.objects.filter(
            departure_airport=dep_airport,
            scheduled_departure__gte=from_date,
            scheduled_departure__lt=to_date
        )


        flights_list = filtered_flights.values('arrival_airport').annotate(
            flight_ids=ArrayAgg('flight_id'),
            avg_flight_time=Avg(F('actual_arrival') - F('actual_departure')),
            flight_count=Count('flight_id')
        )
        results = []
        for fl in flights_list:
            arrival_airport = AirportsData.objects.get(airport_code=fl['arrival_airport'])
            arr_lat = math.radians(arrival_airport.coordinates.y)
            arr_lon = math.radians(arrival_airport.coordinates.x)
            distance_km = round(6371 * math.acos(
                math.cos(dep_lat) * math.cos(arr_lat) *
                math.cos(arr_lon - dep_lon) +
                math.sin(dep_lat) * math.sin(arr_lat)
            ),3)
            passenger_count = TicketFlights.objects.filter(flight_id__in=fl['flight_ids']).count()
            avg_seconds = fl['avg_flight_time'].total_seconds() if fl['avg_flight_time'] else 0
            avg_td = timedelta(seconds=avg_seconds)
            avg_flight_time_str = str(avg_td)  # "HH:MM:SS" format

            results.append({
                'airport_name': arrival_airport.airport_name['en'],
                'distance_km': distance_km,
                'avg_flight_time': avg_flight_time_str,
                'flight_count': fl['flight_count'],
                'passenger_count': passenger_count
            })
        
        results = sorted(results, key=lambda x: x['distance_km'])
        return Response({'data': results})


