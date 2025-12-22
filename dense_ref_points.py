import json
import os
import gpxpy

def interpolate_points(lat, lon):
    """
    Interpolates points between given latitude and longitude arrays.

    Args:
        lat (list): List of latitudes.
        lon (list): List of longitudes.

    Returns:
        tuple: Interpolated latitude and longitude arrays.
    """
    newlat = []
    newlon = []
    for i in range(len(lat) - 1):
        d = gpxpy.geo.haversine_distance(lat[i], lon[i], lat[i + 1], lon[i + 1])
        dnum = int(d / 5)  # Split points for every 5 meters
        newlat.append(lat[i])
        newlon.append(lon[i])
        for j in range(1, dnum + 1):
            newlat.append(lat[i] + j * (lat[i + 1] - lat[i]) / (dnum + 1))
            newlon.append(lon[i] + j * (lon[i + 1] - lon[i]) / (dnum + 1))
    newlat.append(lat[-1])
    newlon.append(lon[-1])
    return newlat, newlon

# Read the slope coordinates from the JSON file
input_file = "json/slopes/ref_points.json"
with open(input_file, 'r', encoding='utf-8') as file:
    runs = json.load(file)

# Process each track in the JSON
for item in runs["items"]:
    for track in item["tracks"]:
        lat = [point["lat"] for point in track["points"]]
        lon = [point["lon"] for point in track["points"]]
        
        # Interpolate the points
        newlat, newlon = interpolate_points(lat, lon)
        
        # Update the track with interpolated points
        track["points"] = [{"lat": lat, "lon": lon} for lat, lon in zip(newlat, newlon)]

# Save the updated structure back to a new file
output_file = "json/slopes/interpolated_ref_points.json"
os.makedirs(os.path.dirname(output_file), exist_ok=True)

with open(output_file, 'w', encoding='utf-8') as file:
    json.dump(runs, file, ensure_ascii=False, indent=4)

print(f"Interpolated points saved to {output_file}")
