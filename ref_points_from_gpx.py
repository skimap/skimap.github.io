# Import the modules
import gpxpy
import json
import os

# Directories
track_directory = "tracks/ref_points/"     

for filename in os.listdir(track_directory):
    if filename.endswith(".gpx"):
        # Open the gpx file and parse it
        with open(track_directory+filename, "r", encoding='utf-8') as f:
            gpx = gpxpy.parse(f)

        # Initialize an empty list for points
        points = []

        # Loop through the tracks, segments, and points of the gpx object
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    # Extract the latitude and longitude of each point
                    lat = point.latitude
                    lon = point.longitude
                    # Append the point as a dictionary to the points list
                    points.append({"lat": lat, "lon": lon})

        name, trackname = filename.split("_")
        name = name.encode("utf-8").decode("unicode-escape")
        trackname = trackname[:-4]

        # Initialize an empty list for tracks
        mytrack = []
        items = []

        # Append a dictionary with trackname and points keys to the tracks list
        mytrack.append({"trackname": trackname, "points": points})

        # Append a dictionary with name and tracks keys to the items list
        items.append({"name": name, "tracks": mytrack})

        # Create the JSON structure
        json_data = {"items": items}

        # # Convert the tracks list to a JSON string, with name as the key and the tracks list as the value
        # json_string = json.dumps({"items": [{"name": name, "tracks": mytrack}]}, indent=4)

        # save the coordinates of the starting points of the ski lifts to a json file
        with open(f'{track_directory}json/{filename[:-4]}.json', 'w') as file:
            json.dump(json_data, file, indent=4)

