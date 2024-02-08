# identfies the corresponding ski slopes and sorts the gpx files according to them
import json
import os

import gpxpy
import numpy as np
import scipy.spatial.distance

def track_minimal_distance_to_point(gpx_track, ref_point):
    """
    Calculates the minimal distance between a gpx track and a reference point in meters.

    Args:
        gpx_track (gpxpy.gpx.GPXTrack): The gpx track to calculate the distance for.
        ref_point (tuple): The reference point as a tuple of (latitude, longitude).

    Returns:
        float: The minimal distance between the gpx track and the reference point.
    """
    return gpxpy.geo.haversine_distance(*gpx_track, *ref_point)

# Directories
base_dir = "c:/zselyigy/dev/skimap/"
track_directory = f"{base_dir}tracks/identification/"     # Tracks to be revised

# read the ref_points.json file
with open("ref_points.json", encoding='utf-8') as f:
    slope_ref_points = json.load(f)

# iterate through all gpx files in the track directory
for filename in os.listdir(track_directory):
    if filename.endswith(".gpx"):
        # print the name of the file
        print(filename)
        # Parse the GPX file
        gpx_file = open(os.path.join(track_directory, filename), 'r')
        gpx = gpxpy.parse(gpx_file)

        # iterate through all ski areas and tracks
        for ski_area in slope_ref_points['items']: # loop over the items list
            for track in ski_area['tracks']: # loop over the tracks list
                #print(ski_area['name'], track['trackname']) # print the name and trackname of each ski area and track
                # iterate over the tracks in the gpx object
                for gpx_track in gpx.tracks:
                    # iterate over the segments in the track
                    for gpx_segment in gpx_track.segments:
                        # convert the list of points to a numpy array of coordinates
                        ref_points = np.array([(p['lat'], p['lon']) for p in track['points']])
                        # convert the gpx segment to a numpy array of coordinates
                        gpx_points = np.array([(p.latitude, p.longitude) for p in gpx_segment.points])
                        # calculate the pairwise distances between the gpx points and the reference points
                        distances = scipy.spatial.distance.cdist(gpx_points, ref_points)
                        # print the minimal distance among all distances
                        print(distances.min())