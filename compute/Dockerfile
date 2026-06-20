# Compute service image. Python 3.12 (not 3.13) because the geospatial wheels — osmnx,
# geopandas, rasterio — are reliably available there; the GDAL stack ships inside the
# manylinux wheels, so no apt-level GDAL is needed for our dependency set.
FROM python:3.12-slim

WORKDIR /srv

# Install the full geospatial stack so `place:` (live OSM) sources work in the container,
# not just the bundled samples. The core would run with requirements.txt alone.
COPY requirements.txt requirements-geo.txt ./
RUN pip install --no-cache-dir -r requirements-geo.txt

COPY app ./app
COPY data ./data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
