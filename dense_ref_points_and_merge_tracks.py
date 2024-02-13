import json
import os
import numpy as np

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
track_directory = "tracks/identification/identified/Síaréna Vibe Park 202402101949/A1/"

# read the slope coordinates from the newslopes.json file
with open("json/slopes/Epleny_slopes.json", 'r', encoding='utf-8') as file:
    runs = json.load(file)

for item in runs["items"]:
    for track in item["tracks"]:
        if track["trackname"] == 'A1':
            lat = []
            lon = []
            ele = []
            for point in track["points"]:
                lat.append(point["lat"])
                lon.append(point["lon"])
                ele.append(point["ele"])   # elevation data will be collected from gpx files


dtot  = 0
newlat = []
newlon = []
newele = []
for i in range(len(lat)-1):
    d = gpxpy.geo.haversine_distance(lat[i], lon[i], lat[i+1], lon[i+1])
    dnum = int(d/5)
    newlat.append(lat[i])
    newlon.append(lon[i])
    newele.append(ele[i])
    for j in range(1,dnum+1):
        newlat.append(lat[i]+j*(lat[i+1]-lat[i])/(dnum+1))
        newlon.append(lon[i]+j*(lon[i+1]-lon[i])/(dnum+1))
        newele.append(ele[i]+j*(ele[i+1]-ele[i])/(dnum+1))

# this will collect the elevation data from the gpx files
elevation_bin = [[] for _ in range(len(newlat))]

# joe is a progress level variable iterates through all files in working directory
joe=1
# Iterate over files in the directory again to add points and lines to the map
for filename in os.listdir(track_directory):
    print(f'{filename} processed, {joe/len(os.listdir(track_directory)) * 100:.2f}% done.')
    if filename.endswith(".gpx"):
        # Parse the GPX file
        gpx_file = open(os.path.join(track_directory, filename), 'r')
        gpx = gpxpy.parse(gpx_file)

        keep_track = True
        for track in gpx.tracks:
            for segment in track.segments:
                for j, point in enumerate(segment.points):
                    mind = np.inf
                    mind_index = -1
                    for i in range(len(newlat)-1):
                        d = gpxpy.geo.haversine_distance(newlat[i], newlon[i], point.latitude, point.longitude)
                        if d < mind:
                            mind = d
                            mind_index = i

                    if j == 0:
                        if abs(newele[mind_index] - point.elevation) > 10:
                            keep_track = False
                    if keep_track:
                        elevation_bin[mind_index].append(point.elevation)
        
        joe += 1

# avg_elevation = []
# with open("elevations.txt", "w", encoding="utf-8") as file:
#     for i in range(len(elevation_bin)):
#         if len(elevation_bin[i]) >0:
#             avg_elevation.append(np.mean(elevation_bin[i]))
#             print(avg_elevation[-1], file = file)

filtered_lat = []
filtered_lon = []
filtered_ele = []
for i in range(len(elevation_bin)):
    if len(elevation_bin[i]) >0:
        filtered_lat.append(newlat[i])
        filtered_lon.append(newlon[i])
        filtered_ele.append(np.mean(elevation_bin[i]))

# Create a new GPX object
gpx = gpxpy.gpx.GPX()

# Create a GPX track
gpx_track = gpxpy.gpx.GPXTrack()
gpx.tracks.append(gpx_track)

# Create a GPX segment
gpx_segment = gpxpy.gpx.GPXTrackSegment()
gpx_track.segments.append(gpx_segment)

# Add points to the segment
for lat, lon, ele in zip(filtered_lat, filtered_lon, filtered_ele):
    gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon, elevation=ele))

# Write the GPX data to a file
filename = 'merged.gpx'
with open(filename, "w") as f:
    f.write(gpx.to_xml())

        