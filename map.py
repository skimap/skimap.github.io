import gpxpy
import folium
import webbrowser

import color as c

# coloring scheme
# 1: green/blue/red/black
# 2: light green/dark green/light blue/dark blue/purple/red/black
# 3: same as 2, but with correct % calculation to max percent 56% (EU)
# 4: same as 2, but with correct % calculation to max percent 45% (HU)

coloring_scheme = 3

# Parse the GPX file
#filename = "tracks/identification/identified/Síaréna Vibe Park/A7+Q3+A1/Morning_Activity_027.gpx"
#filename = "tracks/identification/identified/Sípark Mátraszentistván 202402092051/5+5B/Mátra 5+5B merged filtered 3m.gpx"
#filename = "tracks/to_be_merged/2024-01-28clean.gpx"
filename = "merged.gpx"
gpx_file = open(filename, 'r')
gpx = gpxpy.parse(gpx_file)

# Create a folium map centered around the recorded path
mymap = folium.Map(location=[gpx.tracks[0].segments[0].points[0].latitude,
                             gpx.tracks[0].segments[0].points[0].longitude],
                   zoom_start=15)

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
    if elevation_gain < 0:
        descent_rate = elevation_gain / distance if distance > 0 else 0
    else:
        descent_rate = 0
    descent_rates.append(descent_rate)

# Compute 3-point moving average for descent rates
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
#TODO: Implement color gradient based on previous and next descent rates

# Add points and lines to the map with color-coded descent rate
for i in range(len(latitude_data) - 1):
    folium.PolyLine(
        locations=[[latitude_data[i], longitude_data[i]], [latitude_data[i + 1], longitude_data[i + 1]]],
        color=c.get_color(moving_avg[i], coloring_scheme),
        weight=6
    ).add_to(mymap)

# Save the map as an HTML file
mymap.save(f"{filename[:-4]}-track.html")
#webbrowser.get('windows-default').open_new_tab(f"./{filename[:-4]}-track.html")