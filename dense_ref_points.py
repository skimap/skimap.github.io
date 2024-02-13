import json
import os
import gpxpy

def track_minimal_distance_to_point(gpx_track, ref_point):
    """
    Calculates the minimal distance between a gpx track and a reference point.

    Args:
        gpx_track (gpxpy.gpx.GPXTrack): The gpx track to calculate the distance for.
        ref_point (tuple): The reference point as a tuple of (latitude, longitude).

    Returns:
        float: The minimal distance between the gpx track and the reference point.
    """
    return gpxpy.geo.haversine_distance(*gpx_track, *ref_point)

# Directories
html_directory = "tracks/"

# read the slope coordinates from the newslopes.json file
with open("json/slopes/Epleny_slopes.json", 'r', encoding='utf-8') as file:
    runs = json.load(file)

for item in runs["items"]:
    for track in item["tracks"]:
        if track["trackname"] == 'A1':
            lat = []
            lon = []
            #ele = []
            for point in track["points"]:
                lat.append(point["lat"])
                lon.append(point["lon"])
                #ele.append(point["ele"])   # elevation data will be collected from gpx files


dtot  = 0
newlat = []
newlon = []
for i in range(len(lat)-1):
    d = gpxpy.geo.haversine_distance(lat[i], lon[i], lat[i+1], lon[i+1])
    dnum = int(d/5)
    newlat.append(lat[i])
    newlon.append(lon[i])
    for j in range(1,dnum+1):
        newlat.append(lat[i]+j*(lat[i+1]-lat[i])/(dnum+1))
        newlon.append(lon[i]+j*(lon[i+1]-lon[i])/(dnum+1))

# todo save the new data to a file

# for i in range(len(newlat)-1):
#     d = gpxpy.geo.haversine_distance(newlat[i], newlon[i], newlat[i+1], newlon[i+1])
#     print(d)