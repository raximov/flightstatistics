from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point
from django.db import models

class AircraftsData(models.Model):
    aircraft_code = models.CharField(max_length=3, primary_key=True)
    model = models.JSONField()
    range = models.PositiveIntegerField()

    class Meta:
        db_table = 'aircrafts_data'
        unique_together = ('aircraft_code', 'model')

    def __str__(self):
        return self.aircraft_code


class AirportsData(models.Model):
    airport_code = models.CharField(max_length=3, primary_key=True)
    airport_name = models.JSONField()
    city = models.JSONField()
    coordinates = gis_models.PointField(srid = 4326)
    timezone = models.CharField(max_length=50)

    class Meta:
        db_table = 'airports_data'

    def __str__(self):
        return self.airport_code
    
    def _get_coordinates_db_type(self, connection):
        # Explicitly return the correct PostGIS type and avoid default casting
        return 'geometry(Point, 4326)'

    coordinates._get_db_type = _get_coordinates_db_type


class Bookings(models.Model):
    book_ref = models.CharField(max_length=6, primary_key=True)
    book_date = models.DateTimeField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'bookings'

    def __str__(self):
        return self.book_ref


class Tickets(models.Model):
    ticket_no = models.CharField(max_length=13, primary_key=True)
    book_ref = models.ForeignKey(Bookings, on_delete=models.CASCADE, db_column='book_ref')
    passenger_id = models.CharField(max_length=20)
    passenger_name = models.TextField()
    contact_data = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'tickets'

    def __str__(self):
        return self.ticket_no


class Flights(models.Model):
    flight_id = models.AutoField(primary_key=True)
    flight_no = models.CharField(max_length=6)
    scheduled_departure = models.DateTimeField()
    scheduled_arrival = models.DateTimeField()
    departure_airport = models.ForeignKey(
        AirportsData,
        on_delete=models.PROTECT,
        related_name='departing_flights',
        db_column='departure_airport'
    )
    arrival_airport = models.ForeignKey(
        AirportsData,
        on_delete=models.PROTECT,
        related_name='arriving_flights',
        db_column='arrival_airport'
    )
    status = models.CharField(max_length=20)
    aircraft_code = models.ForeignKey(
        AircraftsData,
        on_delete=models.PROTECT,
        db_column='aircraft_code'
    )
    actual_departure = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'flights'
        unique_together = ('flight_no', 'scheduled_departure')
        indexes = [
            models.Index(fields=['departure_airport', 'scheduled_departure']),
        ]

    def __str__(self):
        return self.flight_no


class Seats(models.Model):
    aircraft_code = models.ForeignKey(AircraftsData, on_delete=models.CASCADE, db_column='aircraft_code')
    seat_no = models.CharField(max_length=4)
    fare_conditions = models.CharField(max_length=10, choices=[('Economy', 'Economy'), ('Comfort', 'Comfort'), ('Business', 'Business')])

    class Meta:
        db_table = 'seats'
        unique_together = ('aircraft_code', 'seat_no')

    def __str__(self):
        return f"{self.aircraft_code}-{self.seat_no}"


class TicketFlights(models.Model):
    ticket_no = models.ForeignKey(Tickets, on_delete=models.CASCADE, db_column='ticket_no')
    flight_id = models.ForeignKey(Flights, on_delete=models.CASCADE, db_column='flight_id')
    fare_conditions = models.CharField(max_length=10, choices=[('Economy', 'Economy'), ('Comfort', 'Comfort'), ('Business', 'Business')])
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'ticket_flights'
        unique_together = ('ticket_no', 'flight_id')


class BoardingPasses(models.Model):
    ticket_no = models.ForeignKey(TicketFlights, on_delete=models.CASCADE, db_column='ticket_no')
    flight_id = models.IntegerField()
    boarding_no = models.IntegerField()
    seat_no = models.CharField(max_length=4)

    class Meta:
        db_table = 'boarding_passes'
        unique_together = ('flight_id', 'boarding_no')
