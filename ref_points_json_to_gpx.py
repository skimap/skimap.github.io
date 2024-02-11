# converts the ref_points.json to gpx tracks of slopes

import json
import os
import shutil

import gpxpy



# Directories
track_directory = "tracks/ref_points/"     # Tracks to be revised

# read the ref_points.json file
with open("ref_points.json", encoding='utf-8') as f:
    slope_ref_points = json.load(f)

for ski_area in slope_ref_points['items']: # loop over the items list
    print(f'Processing ski area {ski_area["name"]}')
    for track in ski_area['tracks']: # loop over the tracks list
        print(f'Current slope: {track["trackname"]}')
        latitudes = []
        longitudes = []
        elevations = [  ]
        for point in track['points']: # loop over the points list
            latitudes.append(point['lat'])
            longitudes.append(point['lon'])
            elevations.append(0)
            
        # Create a new GPX object
        gpx = gpxpy.gpx.GPX()

        # Create a GPX track
        gpx_track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(gpx_track)

        # Create a GPX segment
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)

        # Add points to the segment
        for lat, lon, ele in zip(latitudes, longitudes, elevations):
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon, elevation=ele))

        # Write the GPX data to a file
        filename = f'{track_directory}{ski_area["name"]}_{track["trackname"]}.gpx'
        with open(filename, "w") as f:
            f.write(gpx.to_xml())
