import os
import folium
import gpxpy
import json

import color as c

# Directories
#merge_directory = "tracks/identification/identified/Síaréna Vibe Park/A7+Q3+A1/"     # Tracks to be merged
#merge_directory = "tracks/identification/identified/Sípark Mátraszentistván/5+4/"     # Tracks to be merged
#merge_directory = "tracks/identification/not_found/"     # Tracks to be merged
#merge_directory = "tracks/tracks_to_split/splitted_slides/"
#merge_directory = "tracks/ref_points/"     # Tracks to be merged
merge_directory = "tracks/to_be_merged/"     # Tracks to be merged

# read the last coordinates of the ski lifts
lifts_e = json.load(open('json/lifts/lifts_e.json'))
lift_end_coordinate_tuples = [(lift[1], lift[0]) for lift in lifts_e]    

skiing = 0
# coloring scheme
# 1: green/blue/red/black
# 2: light green/dark green/light blue/dark blue/purple/red/black
# 3: same as 2, but with correct % calculation to max percent 56% (EU)
# 4: same as 2, but with correct % calculation to max percent 45% (HU)
coloring_scheme = 4
color= ""

# create a map centered at mid Europe with a zoom level of 15
mymap = folium.Map(location=[47.85, 16.01], zoom_start=6)
# map_title = '''Sípálya meredekség térképek<br>Van ahol a piros sokszor kék, a kék részben piros vagy olyan zöld, hogy megállsz rajta. Nézd meg, hogy ne érjen meglepetés.'''
# title_html = f'<h3 align="center" style="font-size:16px" >{map_title.encode("utf-8").decode("utf-8")}</h3>'
# mymap.get_root().html.add_child(folium.Element(title_html))

# joe is a progress level variable iterates through all files in working directory
joe=1
# Iterate over files in the directory again to add points and lines to the map
for filename in os.listdir(merge_directory):
    print(f'{filename} processed, {joe/len(os.listdir(merge_directory)) * 100:.2f}% done.')
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
            if color != "#4a412a" and avg1 >= 0 and avg2 >= 0 and avg3 >= 0 and avg4 >= 0 and avg5 >= 0 and avg < 0:
                for point in ref_point:
                    if track_minimal_distance_to_point((latitude_data[i], longitude_data[i]), point) < 50:
                        return True
                return False
            return False
        
        # Add points and lines to the map with color-coded descent rate
        for i in range(len(latitude_data) - 1):
                lift_end_coordinate_tuples_consumable = lift_end_coordinate_tuples
                if check_if_point_is_startingpoint(moving_avg[i-1],
                                                   moving_avg[i-2],
                                                   moving_avg[i-3],
                                                   moving_avg[i-4],
                                                   moving_avg[i-5],
                                                   moving_avg[i],
                                                   i,
                                                   *lift_end_coordinate_tuples_consumable):
                    color = "#4a412a"
                    skiing += 1
                else:
                    color=c.get_color(moving_avg[i], coloring_scheme),
                folium.PolyLine(
                locations=[[latitude_data[i], longitude_data[i]], [latitude_data[i + 1], longitude_data[i + 1]]], weight=6, color=color).add_to(mymap)
    joe += 1

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

# google_analytics_code = """
# <!-- Google tag (gtag.js) -->
# <script async src="https://www.googletagmanager.com/gtag/js?id=G-HLZTNBRD6S"></script>
# <script>
#   window.dataLayer = window.dataLayer || [];
#   function gtag(){dataLayer.push(arguments);}
#   gtag('js', new Date());

#   gtag('config', 'G-HLZTNBRD6S');
# </script>

# <!-- HTML Content -->
# <div class="dropdown">
#     <select onchange="window.location.href = this.value;">
#         <option value="./index.html">Index</option>
#         <option value="./index1.html">Index 1</option>
#         <option value="./index2.html">Index 2</option>
#         <!-- Add more pages here as needed -->
#     </select>
# </div>

# <div id="index" class="page active">Index Page Content</div>
# <div id="index1" class="page">Index 1 Page Content</div>
# <div id="index2" class="page">Index 2 Page Content</div>
# <!-- Add more pages here as needed -->
# """


# Insert the Analytics code just before the closing </head> tag
html_content = html_content.replace("</head>", google_analytics_code + "</head>", 1)

# Write the modified HTML content to a file
with open("skimap.html", "w", encoding="utf-8") as html_file:
    html_file.write(html_content)
    
print(skiing)