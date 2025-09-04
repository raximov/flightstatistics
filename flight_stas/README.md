
# bash da
sudo apt update
sudo apt install postgis postgresql-14-postgis-3
pip install psycopg2-binary


# sql da 
CREATE EXTENSION IF NOT EXISTS postgis;



# settings.py da
INSTALLED_APPS = [
    ...
    'django.contrib.gis',  #PostGIS 
    ... 
]

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',  # PostGIS backend
        ...
    }
}



# sql da
ALTER TABLE airports_data ALTER COLUMN coordinates TYPE geometry(Point, 4326) USING coordinates::geometry;

#models.py
from django.contrib.gis.db import models as gis_models 

class AirportsData(models.Model): 
  # eski: coordinates = models.CharField(max_length=255) 
  coordinates = gis_models.PointField(srid=4326, 
  null=True, blank=True) 
  

python manage.py makemigrations 
python manage.py migrate


