from datetime import timedelta
import math
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse
from django.db import models, connection
from django.db.models import F, Sum, Avg, Count, Value, FloatField, OuterRef, Subquery, DurationField, ExpressionWrapper, IntegerField
from django.db.models import Q
from django.db.models.functions import Cast  # Buni ishlatib ko'ring

from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Func
from django.contrib.gis.db.models import GeometryField
from datetime import timedelta
from django.db.models.functions import Cast

from django.db.models import Count, Sum, Avg, F, Value, IntegerField
from django.db.models.functions import Cast
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import OuterRef, Subquery
from django.contrib.gis.geos import Point




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

    def __init__(self, expr1, expr2, **extra):
        super().__init__(expr1, expr2, **extra)
    
    def as_sql(self, compiler, connection, **extra_context):
        sql, params = super().as_sql(compiler, connection, **extra_context)
        return f"({sql} / 1000.0)", params


    
class FlightStatisticsAPIView(APIView):
    def get(self, request):
        departure_airport_name = request.GET.get('departure_airport_name')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')

        # Departure airportni olish
        dep_airport = AirportsData.objects.get(airport_name__en=departure_airport_name)

        # Passenger count subquery
        passenger_count_subquery = TicketFlights.objects.filter(
            flight_id=OuterRef('pk')
        ).values('flight_id').annotate(
            count=Count('ticket_no')
        ).values('count')[:1]


        filtered_flights = Flights.objects.filter(
            departure_airport=dep_airport,
            scheduled_departure__gte=from_date,
            scheduled_departure__lt=to_date
        ).annotate(
            passenger_count=Subquery(
                passenger_count_subquery, output_field=IntegerField()
            )
        )

        # raise Exception(filtered_flights.values()[0])

        flights_list = filtered_flights.values('arrival_airport__airport_name__en').annotate(
            avg_flight_time=Avg(F('actual_arrival') - F('actual_departure')),
            flight_count=Count('flight_id'),
            distance_km=DistanceSphere(
                F('arrival_airport__coordinates'),
                Value(dep_airport.coordinates, output_field=GeometryField())
            ),
            total_passengers=Sum('passenger_count')
        )

        results = sorted(flights_list, key=lambda x: x['distance_km'] or 0)

        return Response({'data': results})
