from django.contrib import admin
from .models import AircraftsData, AirportsData, Bookings, Flights, TicketFlights


admin.site.register([AircraftsData, AirportsData, Bookings, Flights, TicketFlights])