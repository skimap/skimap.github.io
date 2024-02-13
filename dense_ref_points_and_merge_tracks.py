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
track_directory = "tracks/identification/identified/Síaréna Vibe Park 202402101949/A7+A6/"

# read the slope coordinates from the newslopes.json file
with open("json/slopes/Epleny_slopes.json", 'r', encoding='utf-8') as file:
    runs = json.load(file)

# collect the coordinates and elevation data from the reference slope file
for item in runs["items"]:
    for track in item["tracks"]:
        if track["trackname"] == 'A7+A6':
            lat = []
            lon = []
            ele = []
            for point in track["points"]:
                lat.append(point["lat"])
                lon.append(point["lon"])
                ele.append(point["ele"])   # elevation data will be collected from gpx files

# make the slope coordinates more dense (no more than max_distance_in_m meters is allowed)
max_distance_in_m = 5
dtot  = 0
newlat = []
newlon = []
newele = []
for i in range(len(lat)-1):
    d = gpxpy.geo.haversine_distance(lat[i], lon[i], lat[i+1], lon[i+1])
    dnum = int(d/max_distance_in_m)
    newlat.append(lat[i])
    newlon.append(lon[i])
    newele.append(ele[i])
    for j in range(1,dnum+1):
        newlat.append(lat[i]+j*(lat[i+1]-lat[i])/(dnum+1))
        newlon.append(lon[i]+j*(lon[i+1]-lon[i])/(dnum+1))
        newele.append(ele[i]+j*(ele[i+1]-ele[i])/(dnum+1))

# this collects the descent rate data from the gpx data
rate_bin = [[] for _ in range(len(newlat))]

# joe is a progress level variable iterates through all files in working directory
joe=1
# Iterate over files in the directory again to add points and lines to the map
for filename in os.listdir(track_directory):
    print(f'{filename} processed, {joe/len(os.listdir(track_directory)) * 100:.2f}% done.')
    if filename.endswith(".gpx"):
        # Parse the GPX file
        gpx_file = open(os.path.join(track_directory, filename), 'r')
        gpx = gpxpy.parse(gpx_file)

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

                    # calculate and store the descent rates
                    if j == 0:
                        descent_rate = 0
                    else:
                        distance = gpxpy.geo.haversine_distance(segment.points[j - 1].latitude, segment.points[j - 1].longitude,
                                segment.points[j].latitude, segment.points[j].longitude)
                        elevation_gain = segment.points[j].elevation - segment.points[j-1].elevation
                        if distance != 0:
                            descent_rate = elevation_gain / distance
                        else: 
                            descent_rates=0
                    rate_bin[mind_index].append(descent_rate)
        
        joe += 1

# discard the densed reference points which had no descent rates
filtered_lat = []
filtered_lon = []
filtered_ele = []
filtered_rate = []
for i in range(len(rate_bin)):
    if len(rate_bin[i]) >0:
        filtered_lat.append(newlat[i])
        filtered_lon.append(newlon[i])
        filtered_ele.append(newele[i])
        filtered_rate.append(np.mean(rate_bin[i]))

# Write the results to a new GPX file
# Create a new GPX object
gpx = gpxpy.gpx.GPX()

# Create a GPX track
gpx_track = gpxpy.gpx.GPXTrack()
gpx.tracks.append(gpx_track)

# Create a GPX segment
gpx_segment = gpxpy.gpx.GPXTrackSegment()
gpx_track.segments.append(gpx_segment)

# Add points to the segment
for lat, lon, ele, rate in zip(filtered_lat, filtered_lon, filtered_ele, filtered_rate):
    gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon, elevation=ele, comment=str(rate)))

# Write the GPX data to a file
filename = 'merged Eplény A7+A6.gpx'
with open(filename, "w") as f:
    f.write(gpx.to_xml())

        