import os
import folium
import gpxpy
import html

# Directories
base_dir = "C:/zselyigy/dev/bence20240201/"
merge_directory = f"{base_dir}tracks/to_be_merged/"     # Tracks to be merged
#merge_directory = f"{base_dir}tracks/test/"     # Tracks to be merged

# coloring scheme
# 1: green/blue/red/black
# 2: light green/dark green/light blue/dark blue/purple/red/black
coloring_scheme = 2     

mymap = folium.Map(location=[47.85, 16.01], zoom_start=6)
map_title = '''Sípálya meredekség térképek<br>Van ahol a piros sokszor kék, a kék részben piros vagy olyan zöld, hogy megállsz rajta. Nézd meg, hogy ne érjen meglepetés.'''
title_html = f'<h3 align="center" style="font-size:16px" >{map_title.encode("utf-8").decode("utf-8")}</h3>'
mymap.get_root().html.add_child(folium.Element(title_html))
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
            if elevation_gain < 0:
                descent_rate = elevation_gain / distance
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
                    return '#0000FF'     # blue
                elif rate >= -0.3:
                    return '#800080'     # purple
                elif rate >= -0.37:
                    return 'red'
                elif rate >= -0.45:
                    return 'darkred'
                else:
                    return 'black'

        # Add points and lines to the map with color-coded descent rate
        for i in range(len(latitude_data) - 1):
            folium.PolyLine(
                locations=[[latitude_data[i], longitude_data[i]], [latitude_data[i + 1], longitude_data[i + 1]]],
                color=get_color(moving_avg[i]),
                weight=6
            ).add_to(mymap)

# Save the map as an HTML file
html_content = mymap.get_root().render()

# Append Google Analytics code to the HTML content
google_analytics_code = """
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-HLZTNBRD6S"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-HLZTNBRD6S');
</script>
"""

# Insert the Analytics code just before the closing </head> tag
html_content = html_content.replace("</head>", google_analytics_code + "</head>", 1)

# Write the modified HTML content to a file
with open(os.path.join(base_dir, "index.html"), "w", encoding="utf-8") as html_file:
    html_file.write(html_content)