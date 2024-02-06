# this script splits the raw gps tracks to smaller tranck containing one slides only

import os
import gpxpy

# Directories
base_dir = "C:/zselyigy/dev/skimap/"
merge_directory = f"{base_dir}tracks/tracks_to_split/"     # Tracks to be merged

# Iterate over files in the directory again to add points and lines to the map
for filename in os.listdir(merge_directory):
    if filename.endswith(".gpx"):
        # Parse the GPX file
        gpx_file = open(os.path.join(merge_directory, filename), 'r')
        gpx = gpxpy.parse(gpx_file)

        # Extract latitude, longitude, and elevation data
        latitude_data = []
        longitude_data = []
        elevation_data = []
        descent_rates = []

        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    latitude_data.append(point.latitude)
                    longitude_data.append(point.longitude)
                    elevation_data.append(point.elevation)

        # Calculate descent rate between consecutive points
        for i in range(1, len(elevation_data)):
            distance = gpxpy.geo.haversine_distance(latitude_data[i - 1], longitude_data[i - 1],
                                                    latitude_data[i], longitude_data[i])
            elevation_gain = elevation_data[i] - elevation_data[i - 1]
            if distance != 0:
                descent_rate = elevation_gain / distance
                descent_rates.append(descent_rate)
            else: 
                descent_rates.append(0)

        # Compute 5-point moving average for descent rates
        moving_avg = []
        for i in range(len(descent_rates)):
            if i < 4:
                moving_avg.append(descent_rates[i])
            else:
                avg = (descent_rates[i - 4]
                        + descent_rates[i - 3]
                        + descent_rates[i - 2]
                        + descent_rates[i - 1]
                        + descent_rates[i]
                       ) / 5
                moving_avg.append(avg)

        # Define color based on moving average descent rate

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
        
        def check_if_point_is_startingpoint(avg1, avg2, avg3, avg4, avg5, avg, i, *ref_point):
            """
            Checks if a point is a starting point of a ski slide based on the moving average of the decent rates.

            Args:
                avg1-5 (float): The moving average of the decent rates from the previous five points.
                avg (float): The moving average of the decent rates of the current point.
                i (int): The index of the current point.
                ref_point (tuple): A tuple of reference points to check if the current point is close to any of them.

            Returns:
                bool: True if the current point is a starting point, False otherwise.
            """
            if avg1 >= 0 and avg2 >= 0 and avg3 >= 0 and avg4 >= 0 and avg5 >= 0 and avg < 0:
                for point in ref_point:
                    if track_minimal_distance_to_point((latitude_data[i], longitude_data[i]), point) < 50:
                        return True
                return False
            return False
        

        def create_gpx(latitudes, longitudes, elevations, output_file):
            """
            Creates a GPX file from the given latitudes, longitudes, elevations, and output file path.

            Args:
                latitudes (list): A list of latitudes.
                longitudes (list): A list of longitudes.
                elevations (list): A list of elevations.
                output_file (str): The output file path.

            Returns:
                None
            """
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
            with open(output_file, "w") as f:
                f.write(gpx.to_xml())

        # find the end points of the lifts and split the tracks to slides
        skiing = 1
        # Create a new directory for the split tracks
        try:
            os.mkdir(f'{merge_directory}{filename[:-4]}')
        except:
            pass
        # store the first index of the skiing slide
        first_index = 0
        
        for i in range(len(latitude_data) - 1):
            # the starting points are only a few particular ones in Mátra
            if check_if_point_is_startingpoint(moving_avg[i-1],
                                                moving_avg[i-2],
                                                moving_avg[i-3],
                                                moving_avg[i-4],
                                                moving_avg[i-5],
                                                moving_avg[i],
                                                i,
                                                (47.92128621601892, 19.87078625429176),
                                                (47.92118202312616, 19.873263068969358),
                                                (47.921449210708005, 19.871306204097557)):
                new_filename = f"{merge_directory}{filename[:-4]}/{filename[:-4]}_{skiing:03d}.gpx"     # generate a file name for the new skiing slide
                create_gpx(latitude_data[first_index:i-1],
                            longitude_data[first_index:i-1],
                            elevation_data[first_index:i-1],
                            new_filename)     # create a new GPX file for the new skiing slide
                first_index = i
                skiing += 1
