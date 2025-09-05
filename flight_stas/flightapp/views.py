from datetime import timedelta
import math
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse
from django.db import models, connection
from django.db.models import F, Avg, Count, Value, FloatField
from django.db.models.functions import Cast  
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Func
from django.contrib.gis.db.models import GeometryField
from datetime import timedelta


from .models import AirportsData, Flights, TicketFlights


class FlightStatisticsSQL(APIView):
    def get(self, request):
        departure_airport_name = request.GET.get('departure_airport_name')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        
       
        query = """
        WITH depcity AS (
            SELECT airport_code, coordinates
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
            ROUND(ST_DistanceSphere(d.coordinates, ad.coordinates)::numeric / 1000,3) AS distance_km, 
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

            cursor.execute(query, [departure_airport_name, from_date, to_date])
            results = cursor.fetchall()
                

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
                

class DistanceSphere(Func):
    function = 'ST_DistanceSphere'
    output_field = models.FloatField()

class FlightStatisticsAPIView(APIView):
    def get(self, request):
        departure_airport_name = request.GET.get('departure_airport_name')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')        
        
        dep_airport = AirportsData.objects.get(airport_name__en=departure_airport_name)

        filtered_flights = Flights.objects.filter(
            departure_airport=dep_airport,
            scheduled_departure__gte=from_date,
            scheduled_departure__lt=to_date
        )

        flights_list = filtered_flights.values('arrival_airport').annotate(
            flight_ids=ArrayAgg('flight_id'),
            avg_flight_time=Avg(F('actual_arrival') - F('actual_departure')),
            flight_count=Count('flight_id'),
            distance_m=DistanceSphere(
                F('arrival_airport__coordinates'),
                Value(dep_airport.coordinates, output_field=GeometryField())
            )
        )

        results = []
        for fl in flights_list:
            arrival_airport = AirportsData.objects.get(airport_code=fl['arrival_airport'])
            
            distance_km = fl['distance_m'] / 1000 if fl['distance_m'] else None
            
            passenger_count = TicketFlights.objects.filter(flight_id__in=fl['flight_ids']).count()

            if fl['avg_flight_time']:
                avg_seconds = fl['avg_flight_time'].total_seconds()
                avg_td = timedelta(seconds=avg_seconds)
                avg_flight_time_str = str(avg_td)
            else:
                avg_flight_time_str = None

            results.append({
                'airport_name': arrival_airport.airport_name['en'],
                'distance_km': round(distance_km, 3) if distance_km else None,
                'avg_flight_time': avg_flight_time_str,
                'flight_count': fl['flight_count'],
                'passenger_count': passenger_count
            })
        
        results = sorted(results, key=lambda x: x['distance_km'] or 0)
        return Response({'data': results})


class FlightStatisticsAPIView2(APIView):
    def get(self, request):
        departure_airport_name = request.GET.get('departure_airport_name')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')        
        
        dep_airport = AirportsData.objects.get(airport_name__en=departure_airport_name)

        flights_list = (
            Flights.objects.filter(
                departure_airport=dep_airport,
                scheduled_departure__gte=from_date,
                scheduled_departure__lt=to_date
            )
            .values(
                'arrival_airport',
                'arrival_airport__airport_name',
            )
            .annotate(
                flight_ids=ArrayAgg('flight_id'),
                avg_flight_time=Avg(F('actual_arrival') - F('actual_departure')),
                flight_count=Count('flight_id'),
                distance_km=Cast(
                    DistanceSphere(
                        F('arrival_airport__coordinates'),
                        Value(dep_airport.coordinates, output_field=GeometryField())
                    ) / 1000.0,
                    FloatField()
                ),
                passenger_count=Count('ticketflights__id')
            )
            .order_by('distance_km')
        )

        return Response({'data': list(flights_list)})    