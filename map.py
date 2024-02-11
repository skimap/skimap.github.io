import gpxpy
import folium
import webbrowser

# coloring scheme
# 1: green/blue/red/black
# 2: light green/dark green/light blue/dark blue/purple/red/black
coloring_scheme = 2     

# Parse the GPX file
#filename = "tracks/identification/identified/Síaréna Vibe Park/A7+Q3+A1/Morning_Activity_027.gpx"
#filename = "tracks/identification/identified/Sípark Mátraszentistván 202402092051/5+5B/Mátra 5+5B merged filtered 3m.gpx"
filename = "tracks/2020_01_19_11_23_56.gpx"
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
def get_color(rate):
    if coloring_scheme == 1:
        if rate >= 0:
            return '#80808020'
        elif rate >= -0.15:
            return 'green'
        elif rate >= -0.29:
            return 'blue'
        elif rate >= -0.45:
            return 'red'
        else:
            return 'black'
    if coloring_scheme == 2:
        if rate >= 0:
            return '#80808080'
        elif rate >= -0.07:
            return '#48B748'    # light green
        elif rate >= -0.15:
            return '#006400'     # dark green
        elif rate >= -0.20:
            return '#32A2D9'     # light blue
        elif rate >= -0.25:
            return 'blue'
        elif rate >= -0.3:
            return 'purple'
        elif rate >= -0.45:
            return 'red'
        else:
            return 'black'

# Add points and lines to the map with color-coded descent rate
for i in range(len(latitude_data) - 1):
    folium.PolyLine(
        locations=[[latitude_data[i], longitude_data[i]], [latitude_data[i + 1], longitude_data[i + 1]]],
        color=get_color(moving_avg[i]),
        weight=5
    ).add_to(mymap)

# Save the map as an HTML file
mymap.save(f"{filename[:-4]}-track.html")
webbrowser.open_new_tab(f"{filename[:-4]}-track.html")