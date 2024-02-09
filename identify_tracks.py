# identfies the corresponding ski slopes and sorts the gpx files according to them
# just one gps track and gps segment in a file!

import json
import os
import shutil

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
        # Parse the GPX file
        gpx_file = open(os.path.join(track_directory, filename), 'r')
        gpx = gpxpy.parse(gpx_file)
        gpx_file.close()

        for gpx_track in gpx.tracks:
            # iterate over the segments in the track
            for gpx_segment in gpx_track.segments:
                # convert the gpx segment to a numpy array of coordinates
                gpx_points = np.array([(p.latitude, p.longitude) for p in gpx_segment.points])

        length_gpx_track = gpxpy.geo.haversine_distance(gpx_points[0][0],
                                                        gpx_points[0][1],
                                                        gpx_points[-1][0],
                                                        gpx_points[-1][1])

        smallest_avg_distance = np.inf
        closest_ski_area = None
        closest_ski_track = None
        # iterate through all ski areas and tracks
        for ski_area in slope_ref_points['items']: # loop over the items list
            for track in ski_area['tracks']: # loop over the tracks list
                #print(ski_area['name'], track['trackname']) # print the name and trackname of each ski area and track
                # convert the list of points to a numpy array of coordinates
                ref_points = np.array([(p['lat'], p['lon']) for p in track['points']])
                # calculate the pairwise distances between the gpx points and the reference points
                distances = scipy.spatial.distance.cdist(gpx_points, ref_points)
                # calculate the minimal values for each reference point
                min_values = np.min(distances, axis=0)
                avg_distance = np.mean(min_values)
                # find the length of the slopes
                length_track = gpxpy.geo.haversine_distance(ref_points[0][0],
                                                ref_points[0][1],
                                                ref_points[-1][0],
                                                ref_points[-1][1])
                rel_length_diff = length_track / length_gpx_track
                print(f'{ski_area["name"]}, {track["trackname"]}, {avg_distance}, {rel_length_diff}')
                if (avg_distance < smallest_avg_distance) and (abs(rel_length_diff - 1) < 0.1):
                    smallest_avg_distance = avg_distance
                    closest_ski_area = ski_area["name"]
                    closest_ski_track = track["trackname"]
                            
        # print the closest ski area and track                       
        print(f'{filename}: the closest ski area and track is {closest_ski_area}, {closest_ski_track} with avg distance {smallest_avg_distance}.')
        
        # in case the distance is too large we put file in directory not_found
        if smallest_avg_distance > 0.01:
            shutil.move(track_directory+filename, f'{track_directory}not_found/{filename}')
        else:
            # create the {track_directory}/identified/{closest_ski_area}/{closest_ski_track}/{filename}.gpx file
            try:
                os.mkdir(f'{track_directory}identified/{closest_ski_area}')
            except:
                pass
            try:
                os.mkdir(f'{track_directory}identified/{closest_ski_area}/{closest_ski_track}')
            except:
                pass
            shutil.move(track_directory+filename, f'{track_directory}identified/{closest_ski_area}/{closest_ski_track}/{filename}')
