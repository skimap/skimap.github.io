import os
import json
import gpxpy
from shapely.geometry import LineString, shape, Polygon, MultiPolygon, Point
from geopy.distance import distance

# ------------------------------------------------------
# Load ski areas GeoJSON
# ------------------------------------------------------
with open("json/ski_areas/ski_areas.geojson", encoding="utf-8") as f:
    ski_areas_data = json.load(f)


# ------------------------------------------------------
# Classify a track by proximity (2 km) to ski area
# ------------------------------------------------------
def classify_track(points, ski_areas, max_km=2):
    # Build LineString from track points
    line = LineString([(lon, lat) for lat, lon, _ in points])
    centroid = line.centroid  # shapely Point

    for feature in ski_areas["features"]:
        name = feature["properties"].get("name", "Unknown")
        geom = shape(feature["geometry"])

        # If centroid is inside geometry → match
        if geom.contains(centroid):
            return name, (centroid.y, centroid.x)

        # Only for Polygon or MultiPolygon → check distance
        if isinstance(geom, (Polygon, MultiPolygon)):
            polygons = [geom] if isinstance(geom, Polygon) else geom.geoms
            min_dist = min(
                min(distance((centroid.y, centroid.x), (lat, lon)).km
                    for lon, lat in poly.exterior.coords)
                for poly in polygons
            )
            if min_dist <= max_km:
                return name, (centroid.y, centroid.x)

        # Optionally: for Point geometry → check distance
        elif isinstance(geom, Point):
            if distance((centroid.y, centroid.x), (geom.y, geom.x)).km <= max_km:
                return name, (centroid.y, centroid.x)

        # LineString could also be checked if desired

    # Fallback: no match
    return "Unknown", (centroid.y, centroid.x)


# ------------------------------------------------------
# Test all tracks in folder
# ------------------------------------------------------
track_folder = "tracks/processed/all"

for file in os.listdir(track_folder):
    if not file.endswith(".gpx"):
        continue

    gpx_path = os.path.join(track_folder, file)
    with open(gpx_path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    for track in gpx.tracks:
        for segment in track.segments:
            points = [(p.latitude, p.longitude, p.elevation) for p in segment.points]
            ski_area_name, centroid_coords = classify_track(points, ski_areas_data)

            print(f"{file}: {ski_area_name}, centroid={centroid_coords}")
