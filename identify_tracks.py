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
track_directory = "tracks/identification/"     # Tracks to be revised

# read the ref_points.json file
with open("json/slopes/ref_points.json", encoding='utf-8') as f:
    slope_ref_points = json.load(f)

# open a log file identify.log
log_file = open(f"{track_directory}identify.log", "w", encoding="utf-8")


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

        length_gpx_list = [gpxpy.geo.haversine_distance(gpx_points[i][0],
                                        gpx_points[i][1],
                                        gpx_points[i+1][0],
                                        gpx_points[i+1][1]) for i in range(len(gpx_points) - 1)]
        length_gpx_track = np.sum(length_gpx_list)

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
                length_track_list = [gpxpy.geo.haversine_distance(ref_points[i][0],
                                                ref_points[i][1],
                                                ref_points[i+1][0],
                                                ref_points[i+1][1]) for i in range(len(ref_points) - 1)]
                length_track = np.sum(length_track_list)
                rel_length_diff = length_track / length_gpx_track
                abs_length_diff = np.abs(length_track - length_gpx_track)
                distance_of_starting_points = gpxpy.geo.haversine_distance(ref_points[0][0],
                                                ref_points[0][1],
                                                gpx_points[0][0],
                                                gpx_points[0][1])
                distance_of_end_points = gpxpy.geo.haversine_distance(ref_points[-1][0],
                                                ref_points[-1][1],
                                                gpx_points[-1][0],
                                                gpx_points[-1][1])
                print(f'{ski_area["name"]}, {track["trackname"]}, {avg_distance}, {length_gpx_track}, {length_track}, {rel_length_diff}, {abs_length_diff}, {distance_of_starting_points}, {distance_of_end_points}', file= log_file)
                if (avg_distance < smallest_avg_distance) and ((abs(rel_length_diff - 1) < 0.13) or (abs_length_diff < 40)) and (distance_of_starting_points < 70) and (distance_of_end_points< 70):
                    smallest_avg_distance = avg_distance
                    closest_ski_area = ski_area["name"]
                    closest_ski_track = track["trackname"]
                            
        # print the closest ski area and track               
        if (closest_ski_area == None) and (closest_ski_track == None):         
            print(f'{filename}: no fitting ski area + slope found.', file= log_file)
            print(f'{filename}: no fitting ski area + slope found.')
        else:
            print(f'{filename}: the closest ski area and slope is {closest_ski_area}, {closest_ski_track} with avg distance {smallest_avg_distance}.', file= log_file)
            print(f'{filename}: the closest ski area and slope is {closest_ski_area}, {closest_ski_track} with avg distance {smallest_avg_distance}.')
        
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
