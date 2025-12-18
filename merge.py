#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import gpxpy
import numpy as np
import shapely.geometry as geom
from geopy.distance import distance as geo_distance
from folium.plugins import LocateControl
from PIL import Image, ImageDraw
import numpy as np
import time
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
import numba
import argparse
from branca.element import MacroElement, Template
import shapely.geometry as geom
from geopy.distance import distance as geo_distance
import subprocess
import sys

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
MERGE_DIRECTORY = "tracks/raw/all"
OUTPUT_GEOJSON_DIR = "tracks_geojson"
TILES_OUTPUT_DIR = "tiles"
SKI_AREAS_FILE = "json/ski_areas/ski_areas.geojson"
LIFTS_FILE = "json/lifts/lifts_e.json"
MAX_FEATURES_PER_FILE = 10000

# Constants
EARTH_RADIUS = 6371000  # meters
DEG_TO_RAD = math.pi / 180.0

# -----------------------------------------------------------------------------
# DATA LOADING
# -----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_lift_data():
    """Load lift coordinates for proximity checks."""
    try:
        with open(LIFTS_FILE) as f:
            lifts_e = json.load(f)
        return [(lift[1], lift[0]) for lift in lifts_e]
    except FileNotFoundError:
        print(f"Warning: {LIFTS_FILE} not found. Lift coloring disabled.")
        return []

@lru_cache(maxsize=1)
def load_ski_areas_data():
    """Load ski area polygons for resort assignment."""
    try:
        with open(SKI_AREAS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {SKI_AREAS_FILE} not found. Resort selector will be empty.")
        return {"features": []}

lift_end_coordinate_tuples = load_lift_data()
ski_areas_data = load_ski_areas_data()

# -----------------------------------------------------------------------------
# MATH & GEOMETRY HELPERS
# -----------------------------------------------------------------------------

@numba.jit(nopython=True)
def haversine_distance_vectorized(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * DEG_TO_RAD
    dlon = (lon2 - lon1) * DEG_TO_RAD
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1 * DEG_TO_RAD) * np.cos(lat2 * DEG_TO_RAD) * np.sin(dlon / 2.0)**2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return EARTH_RADIUS * c

def assign_ski_area(points, max_km=2):
    """
    Determines the ski area name for a set of points using geometric containment
    or proximity.
    """
    if not points or not ski_areas_data.get("features"):
        return "Unknown"

    try:
        # Optimization: Use a simplified subset of points to form a line
        step = max(1, len(points) // 50)
        sample_points = points[::step]
        line = geom.LineString([(lon, lat) for lat, lon, _ in sample_points])
        centroid = line.centroid
        
        for feature in ski_areas_data["features"]:
            # FIX: Robust name retrieval handling None/null
            props = feature.get("properties", {})
            if not props:
                continue
            name = props.get("name")
            if not name: 
                continue # Skip unnamed features

            try:
                geometry = geom.shape(feature["geometry"])
            except Exception:
                continue

            # 1. Check Contains (Fastest)
            if geometry.contains(centroid):
                return name

            # 2. Check Distance
            dist_km = float("inf")
            feature_center = geometry.centroid
            dist_to_center = geo_distance((centroid.y, centroid.x), (feature_center.y, feature_center.x)).km
            
            if dist_to_center < max_km * 2: 
                if dist_to_center <= max_km:
                    return name

    except Exception:
        pass
    
    return "Unknown"

# -----------------------------------------------------------------------------
# PROCESSING WORKER
# -----------------------------------------------------------------------------

def process_gpx_file_optimized(filename):
    """
    Parses GPX, smoothing data, calculating gradients, and determining ski area.
    """
    filepath = os.path.join(MERGE_DIRECTORY, filename)
    try:
        with open(filepath, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    points.append((point.latitude, point.longitude, point.elevation))

        if len(points) < 2:
            return ([], 0, "Unknown", None)

        # 1. Determine Ski Area & Centroid
        try:
            area_name = assign_ski_area(points)
            avg_lat = sum(p[0] for p in points) / len(points)
            avg_lon = sum(p[1] for p in points) / len(points)
            centroid_coords = (avg_lat, avg_lon)
        except Exception:
            area_name = "Unknown"
            centroid_coords = None

        # 2. Vectorized Processing (Numpy)
        pts_np = np.array(points)
        lats = pts_np[:, 0]
        lons = pts_np[:, 1]
        eles = pts_np[:, 2]

        dists = haversine_distance_vectorized(lats[:-1], lons[:-1], lats[1:], lons[1:])
        ele_diffs = eles[1:] - eles[:-1]
        
        safe_dists = np.where(dists == 0, 1e-6, dists)
        gradients = ele_diffs / safe_dists

        grad_padded = np.pad(gradients, (2, 2), mode='edge')
        smoothed_grads = np.convolve(grad_padded, np.ones(5)/5, mode='valid')

        skiing_dist = np.sum(dists[smoothed_grads < -0.07])
        
        return (points, skiing_dist, area_name, centroid_coords)

    except Exception as e:
        print(f"Error processing {filename}: {str(e)}")
        return ([], 0, "Unknown", None)

# -----------------------------------------------------------------------------
# MAP GENERATION
# -----------------------------------------------------------------------------

def generate_optimized_map(ski_areas_map=None):
    """
    Generates the Folium map with snowy base and JS selector.
    """
    
    # 1. Initialize Map
    mymap = folium.Map(
        location=[47.85, 16.01],
        zoom_start=6,
        max_zoom=19,
        prefer_canvas=True,
        tiles="CartoDB Positron",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
    )
    
    LocateControl(
        auto_start=False,
        strings={"title": "Show my location"},
        position="topright"
    ).add_to(mymap)
    
    # 2. Add The Ski Tracks Layer
    import time
    cache_buster = str(int(time.time()))
    
    ski_layer = folium.TileLayer(
        tiles=f'tiles/{{z}}/{{x}}/{{y}}.png?{cache_buster}',
        attr='Ski Tracks',
        name='Ski Tracks',
        min_zoom=10,
        max_zoom=19,
        overlay=True,
        detectRetina=True,
        crossOrigin='anonymous',
        opacity=0.9,
        errorTileUrl='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
    )
    ski_layer.add_to(mymap)
    
    # 3. JavaScript Logic: Resort Selector
    
    if ski_areas_map:
        # FIX: Filter out any non-string keys before sorting
        valid_items = {k: v for k, v in ski_areas_map.items() if k and isinstance(k, str)}
        sorted_areas = sorted(valid_items.items())
        
        areas_js = json.dumps(valid_items)
        
        options_html = '<option value="">Jump to Ski Area...</option>'
        for name, coords in sorted_areas:
            safe_name = name.replace("'", "&#39;")
            options_html += f'<option value="{safe_name}">{safe_name}</option>'
    else:
        areas_js = "{}"
        options_html = '<option value="">No areas found</option>'

    map_id = mymap.get_name()
    layer_id = ski_layer.get_name()

    js_template = f"""
    {{% macro script(this, kwargs) %}}
        var map = {map_id};
        var skiLayer = {layer_id};
        var skiAreas = {areas_js};

        console.log("Ski Map Initialized");

        // --- Resort Selector ---
        var selectorControl = L.control({{position: 'topright'}});
        
        selectorControl.onAdd = function (map) {{
            var div = L.DomUtil.create('div', 'info legend');
            div.innerHTML = '<select id="area_selector" style="font-size: 14px; padding: 8px; border-radius: 4px; border: 1px solid #ccc; box-shadow: 0 1px 5px rgba(0,0,0,0.4); background: white;">' + 
                            '{options_html}' + 
                            '</select>';
            L.DomEvent.disableClickPropagation(div);
            L.DomEvent.disableScrollPropagation(div);
            return div;
        }};
        
        selectorControl.addTo(map);
        
        var sel = document.getElementById("area_selector");
        if (sel) {{
            sel.addEventListener("change", function(e) {{
                var val = e.target.value;
                if(val && skiAreas[val]) {{
                    map.flyTo(skiAreas[val], 13, {{
                        animate: true,
                        duration: 1.5
                    }});
                }}
            }});
        }}

        // --- Tile Error Handling ---
        skiLayer.on('tileerror', function(error) {{
            var img = error.tile;
            var src = img.src;
            if (src.includes('&retry=')) return;
            setTimeout(function() {{
                var sep = src.includes('?') ? '&' : '?';
                img.src = src + sep + 'retry=' + Date.now();
            }}, 1000);
        }});

        window.addEventListener("orientationchange", function() {{
            setTimeout(function(){{ map.invalidateSize(); }}, 200);
        }});

    {{% endmacro %}}
    """
    
    macro = MacroElement()
    macro._template = Template(js_template)
    mymap.get_root().add_child(macro)
    
    return mymap

# -----------------------------------------------------------------------------
# MAIN EXECUTION
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Merge GPX tracks and generate Ski Map.")
    parser.add_argument('--html-only', action='store_true', help="Skip tile generation, just regenerate HTML")
    args = parser.parse_args()
    
    # 1. Rust Tile Generation
    if not args.html_only:
        print("Step 1: Running High-Performance Rust Renderer...")
        if os.path.exists("ski_renderer.exe"):
            try:
                subprocess.run(["ski_renderer.exe"], check=True)
            except subprocess.CalledProcessError:
                print("Error: Rust renderer failed.")
                sys.exit(1)
        else:
            print("Warning: ski_renderer.exe not found. Skipping tile generation.")
    
    # 2. Process Data for Metadata
    print("Step 2: Scanning tracks for Ski Resort locations...")
    
    found_ski_areas = defaultdict(list)
    files = [f for f in os.listdir(MERGE_DIRECTORY) if f.endswith('.gpx')]
    
    with ProcessPoolExecutor(max_workers=mp.cpu_count()) as executor:
        futures = {executor.submit(process_gpx_file_optimized, f): f for f in files}
        
        for future in tqdm(as_completed(futures), total=len(files), desc="Indexing Resorts"):
            try:
                _, _, area_name, centroid = future.result()
                
                # FIX: Ensure area_name is a valid string before storing
                if area_name and area_name != "Unknown" and centroid is not None:
                    found_ski_areas[area_name].append(centroid)
            except Exception as e:
                continue

    final_area_map = {}
    for name, coords_list in found_ski_areas.items():
        if coords_list:
            avg_lat = sum(c[0] for c in coords_list) / len(coords_list)
            avg_lon = sum(c[1] for c in coords_list) / len(coords_list)
            final_area_map[name] = [avg_lat, avg_lon]
            
    print(f"Found {len(final_area_map)} ski areas.")

    # 3. Generate HTML
    print("Step 3: Generating Final HTML Map...")
    mymap = generate_optimized_map(final_area_map)
    
    google_analytics = """
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-HLZTNBRD6S"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-HLZTNBRD6S');
    </script>
    """
    
    custom_css = """
    <style>
    .leaflet-tile {
        image-rendering: -webkit-optimize-contrast;
        image-rendering: crisp-edges;
        image-rendering: pixelated;
    }
    .leaflet-container {
        background: #f0f0f0;
    }
    </style>
    """

    html_content = mymap.get_root().render()
    
    if "</head>" in html_content:
        injection = google_analytics + custom_css
        html_content = html_content.replace("</head>", injection + "</head>", 1)
        
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print("Done! Open index.html to view your Snowy Ski Map.")

if __name__ == "__main__":
    main()
