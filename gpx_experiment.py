import os
import folium
import gpxpy
import json
from collections import defaultdict
import color as c
from tqdm import tqdm
from folium.plugins import LocateControl
from jinja2 import Template

# Configuration
merge_directory = "tracks/raw/Ivett Ördög/new/"
coloring_scheme = 1
output_geojson_dir = "tracks_geojson"
min_zoom_level = 10
os.makedirs(output_geojson_dir, exist_ok=True)

# Load lift data
with open('json/lifts/lifts_e.json') as f:
    lifts_e = json.load(f)
lift_end_coordinate_tuples = [(lift[1], lift[0]) for lift in lifts_e]

def process_gpx_file(filename):
    try:
        file_path = os.path.join(merge_directory, filename)
        with open(file_path, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        points = []
        for track in gpx.tracks:
            for segment in track.segments:
                points.extend([(p.latitude, p.longitude, p.elevation) for p in segment.points])

        if len(points) < 2:
            return (defaultdict(list), 0)

        # Calculate descent rates and moving average
        descent_rates = []
        for i in range(1, len(points)):
            distance = gpxpy.geo.haversine_distance(
                points[i-1][0], points[i-1][1],
                points[i][0], points[i][1]
            )
            elevation_gain = points[i][2] - points[i-1][2]
            descent_rates.append(elevation_gain / distance if distance != 0 else 0)

        moving_avg = [sum(descent_rates[max(0,i-4):i+1])/5 for i in range(len(descent_rates))]

        # Process segments as individual features
        color_groups = defaultdict(list)
        skiing = 0

        for i in range(len(points) - 1):  # Process each segment
            if i >= len(moving_avg):
                break

            current_point = (points[i][0], points[i][1])
            next_point = (points[i+1][0], points[i+1][1])

            # Determine color for this segment
            if i >= 5 and all(m >= 0 for m in moving_avg[i-5:i]) and moving_avg[i] < 0:
                if any(gpxpy.geo.haversine_distance(*current_point, *lift) < 50 for lift in lift_end_coordinate_tuples):
                    color = "#4a412a"
                    skiing += 1
                else:
                    color = c.get_color(moving_avg[i], coloring_scheme)
            else:
                color = c.get_color(moving_avg[i], coloring_scheme)

            # Create a LineString for each segment
            color_groups[color].append([current_point, next_point])

        return (color_groups, skiing)
    except Exception as e:
        print(f"Error processing {filename}: {str(e)}")
        return (defaultdict(list), 0)

def generate_geojson(color_groups):
    features = []
    for color, segments in color_groups.items():
        for segment in segments:
            if len(segment) < 2:
                continue
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for lat, lon in segment]
                },
                "properties": {
                    "color": color,
                    "min_zoom": min_zoom_level
                }
            })
    
    geojson_path = os.path.join(output_geojson_dir, "tracks.geojson")
    with open(geojson_path, 'w') as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    
    return geojson_path

def generate_map(geojson_path):
    mymap = folium.Map(location=[47.85, 16.01], zoom_start=6)
    
    # Add locate control
    LocateControl(
        auto_start=False,
        strings={"title": "Show my location"},
        position="topright",
        locate_options={"enableHighAccuracy": True}
    ).add_to(mymap)

    # Add tracks layer with explicit identifier
    geojson_layer = folium.GeoJson(
        geojson_path,
        style_function=lambda feature: {
            'color': feature['properties']['color'],
            'weight': 8,
            'opacity': 0  # Start hidden
        },
        name='ski_tracks',
        overlay=True,
        control=False
    ).add_to(mymap)
    
    # Get layer's JS variable name
    layer_name = geojson_layer.get_name()

    # Simplified zoom handling
    script = f"""
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        const map = window['{mymap.get_name()}'];
        const MIN_ZOOM = {min_zoom_level};
        let trackLayer = {layer_name};

        function updateVisibility() {{
            const currentZoom = map.getZoom();
            trackLayer.setStyle({{ opacity: currentZoom >= MIN_ZOOM ? 1 : 0 }});
        }}

        map.whenReady(function() {{
            // Initial update
            updateVisibility();
            // Update on zoom
            map.on('zoomend', updateVisibility);
        }});
    }});
    </script>
    """
    
    mymap.get_root().html.add_child(folium.Element(script))
    return mymap

def main():
    color_groups = defaultdict(list)
    total_skiing = 0

    files = [f for f in os.listdir(merge_directory) if f.endswith(".gpx")]
    for filename in tqdm(files, desc="Processing tracks"):
        groups, skiing = process_gpx_file(filename)
        for color, lines in groups.items():
            color_groups[color].extend(lines)
        total_skiing += skiing

    geojson_path = generate_geojson(color_groups)
    mymap = generate_map(geojson_path)
    
    # Add Google Analytics
    google_analytics = """
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-HLZTNBRD6S"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', 'G-HLZTNBRD6S');
    </script>
    """
    
    html_content = mymap.get_root().render()
    html_content = html_content.replace("</head>", google_analytics + "</head>", 1)
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nTotal skiing segments detected: {total_skiing}")
    print("Map generated: skimap.html")
    print("Note: Test using a local web server: python -m http.server 8000")

if __name__ == "__main__":
    main()