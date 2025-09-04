#  PostGIS PointField

## 1️⃣ PostgreSQL / PostGIS o‘rnatish

```bash
sudo apt update
sudo apt install postgis postgresql-14-postgis-3
pip install psycopg2-binary
```


---

## 2️⃣ PostGIS extension yaratish

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

---

## 3️⃣ Django `settings.py` konfiguratsiyasi

```python
INSTALLED_APPS = [
    ...
    'django.contrib.gis',  #  PostGIS qo‘shildi
    ...
]

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',  #  PostGIS backend
        ...
    }
}
```

---

## 4️⃣ AirportsData modelini o'tkazish
```python
from django.contrib.gis.db import models as gis_models

class AirportsData(models.Model):
    coordinates = gis_models.PointField(srid=4326, null=True, blank=True)
```

---

## 5️⃣ SQL orqali type o‘zgartirish 
```sql
ALTER TABLE airports_data
ALTER COLUMN coordinates TYPE geometry(Point, 4326)
USING coordinates::geometry;
```


---

## 6️⃣ Django migratsiya yurgazish

```bash
python manage.py makemigrations
python manage.py migrate
```


