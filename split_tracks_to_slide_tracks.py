import json
import os
import gpxpy


# Directories
split_directory = "tracks/tracks_to_split/"  # Tracks to be split
html_directory = "htmls/splitted_slides/"  # HTML files to be created

# Read the first coordinates of the ski lifts
lifts_s = json.load(open('json/lifts/lifts_s.json'))
lift_start_coordinate_tuples = [(lift[1], lift[0]) for lift in lifts_s]  # Latitude and longitude are often switched

# Read the last coordinates of the ski lifts
lifts_e = json.load(open('json/lifts/lifts_e.json'))
lift_end_coordinate_tuples = [(lift[1], lift[0]) for lift in lifts_e]  # Latitude and longitude are often switched


# Define utility functions
def track_minimal_distance_to_point(gpx_track, ref_point):
    """
    Calculates the minimal distance between a gpx track and a reference point in meters.
    """
    return gpxpy.geo.haversine_distance(*gpx_track, *ref_point)


def check_if_point_is_startingpoint(avg1, avg2, avg3, avg4, avg5, avg, i, *ref_point):
    """
    Checks if a point is a starting point of a ski slide based on the moving average of the descent rates.
    """
    if avg1 >= 0 and avg2 >= 0 and avg3 >= 0 and avg4 >= 0 and avg5 >= 0 and avg < 0:
        for point in ref_point:
            if track_minimal_distance_to_point((latitude_data[i], longitude_data[i]), point) < 50:
                return True
    return False


def check_if_point_is_endpoint(avg1, avg2, avg3, avg4, avg5, avg, i, *ref_point):
    """
    Checks if a point is an endpoint of a ski slide based on the moving average of the descent rates.
    """
    if avg1 <= 0 and avg2 <= 0 and avg3 <= 0 and avg4 <= 0 and avg5 <= 0 and avg > 0:
        for point in ref_point:
            if track_minimal_distance_to_point((latitude_data[i], longitude_data[i]), point) < 50:
                return True
    return False


def create_gpx(latitudes, longitudes, elevations, output_file):
    """
    Creates a GPX file from the given latitudes, longitudes, elevations, and output file path.
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


def save_track_to_html(filename, latitude, longitude, moving_avg):
    """
    Saves the ski slide data as an HTML map file.
    """
    import folium
    import color as c

    # Create a map centered at the first point
    mymap = folium.Map(location=[latitude[0], longitude[0]], zoom_start=16)
    title_html = f'<h3 align="center" style="font-size:16px" >{filename}</h3>'
    mymap.get_root().html.add_child(folium.Element(title_html))

    for i in range(len(latitude) - 1):
        folium.PolyLine(
            locations=[[latitude[i], longitude[i]], [latitude[i + 1], longitude[i + 1]]],
            weight=6,
            color=c.get_color(moving_avg[i], 4)
        ).add_to(mymap)

    # Save the map as an HTML file
    html_content = mymap.get_root().render()

    # Create the full path for the HTML file
    html_path = os.path.join(html_directory, f"{filename}.html")

    # Ensure the directory exists
    os.makedirs(os.path.dirname(html_path), exist_ok=True)

    # Write the HTML file
    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)


# Iterate over files in the directory to process
for filename in os.listdir(split_directory):
    if filename.endswith(".gpx"):
        # Parse the GPX file
        gpx_file = open(os.path.join(split_directory, filename), 'r')
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
            descent_rates.append(elevation_gain / distance if distance != 0 else 0)

        # Compute 5-point moving average for descent rates
        moving_avg = [
            sum(descent_rates[max(0, i - 4):i + 1]) / min(5, i + 1) for i in range(len(descent_rates))
        ]

        # Find the endpoints of the lifts and split the tracks into slides
        skiing = 1
        os.makedirs(f'{split_directory}splitted_slides', exist_ok=True)  # Ensure directory exists
        first_index = 0  # Store the first index of the skiing slide

        for i in range(len(latitude_data) - 1):
            if check_if_point_is_endpoint(
                moving_avg[i - 1], moving_avg[i - 2], moving_avg[i - 3],
                moving_avg[i - 4], moving_avg[i - 5], moving_avg[i], i, *lift_start_coordinate_tuples
            ):
                new_filename = f"{filename[:-4]}_{skiing:03d}"  # Generate base filename
                create_gpx(
                    latitude_data[first_index:i - 1],
                    longitude_data[first_index:i - 1],
                    elevation_data[first_index:i - 1],
                    f"{split_directory}splitted_slides/{new_filename}.gpx"
                )
                save_track_to_html(
                    new_filename,
                    latitude_data[first_index:i - 1],
                    longitude_data[first_index:i - 1],
                    moving_avg[first_index:i - 1]
                )
                print(f"Slide {skiing} was created from {filename}.")
                skiing += 1

            if check_if_point_is_startingpoint(
                moving_avg[i - 1], moving_avg[i - 2], moving_avg[i - 3],
                moving_avg[i - 4], moving_avg[i - 5], moving_avg[i], i, *lift_end_coordinate_tuples
            ):
                first_index = i  # Update the start index of the next slide
