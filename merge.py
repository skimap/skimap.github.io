#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import folium
import gpxpy
import json
import math
from collections import defaultdict
from tqdm import tqdm
from folium.plugins import LocateControl
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

# Try importing B2SDK for uploading
try:
    from b2sdk.v2 import InMemoryAccountInfo, B2Api
    B2_AVAILABLE = True
except ImportError:
    B2_AVAILABLE = False

# NOTE: color is imported here. If you have a local color.py file, keep this. 
try:
    import color as c
except ImportError:
    pass

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
MERGE_DIRECTORY = "tracks/raw/all"
OUTPUT_GEOJSON_DIR = "tracks_geojson"
TILES_OUTPUT_DIR = "tiles"
SKI_AREAS_FILE = "json/ski_areas/ski_areas.geojson"
LIFTS_FILE = "json/lifts/lifts_e.json"

# --- BACKBLAZE B2 CONFIGURATION ---
# 1. Fill these in with your details
B2_KEY_ID = "YOUR_KEY_ID_HERE"           # e.g., 0023a...
B2_APP_KEY = "YOUR_APP_KEY_HERE"         # e.g., K002...
B2_BUCKET_NAME = "YOUR_BUCKET_NAME"      # e.g., my-ski-map
# 2. The URL must end with a slash '/'. 
# Check B2 file info to find your "f00x" subdomain.
B2_FRIENDLY_URL = "https://f002.backblazeb2.com/file/YOUR_BUCKET_NAME/" 

# Set this to True to use B2 tiles, or False to use local tiles
USE_REMOTE_TILES = True 

# Constants
EARTH_RADIUS = 6371000
DEG_TO_RAD = math.pi / 180.0

# -----------------------------------------------------------------------------
# DATA LOADING
# -----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_lift_data():
    try:
        with open(LIFTS_FILE) as f:
            lifts_e = json.load(f)
        return [(lift[1], lift[0]) for lift in lifts_e]
    except FileNotFoundError:
        return []

@lru_cache(maxsize=1)
def load_ski_areas_data():
    try:
        with open(SKI_AREAS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"features": []}

lift_end_coordinate_tuples = load_lift_data()
ski_areas_data = load_ski_areas_data()

# -----------------------------------------------------------------------------
# B2 UPLOAD WORKER
# -----------------------------------------------------------------------------

def sync_tiles_to_b2():
    """Syncs the local 'tiles' folder to the B2 bucket."""
    if not B2_AVAILABLE:
        print("Error: b2sdk is not installed. Run 'pip install b2sdk'")
        return

    print("\n--- Starting B2 Upload ---")
    print(f"Target Bucket: {B2_BUCKET_NAME}")
    
    try:
        info = InMemoryAccountInfo()
        b2_api = B2Api(info)
        b2_api.authorize_account("production", B2_KEY_ID, B2_APP_KEY)
        
        bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)
        
        source_folder = os.path.abspath(TILES_OUTPUT_DIR)
        destination_folder = "tiles" # Folder name inside the bucket

        print(f"Syncing {source_folder} -> B2:/{destination_folder}...")
        
        # Using the synchronize API (like rsync)
        from b2sdk.v2 import Synchronizer, ScanPolicies
        
        # Simple sync policy
        synchronizer = Synchronizer(
            max_workers=10,
            dry_run=False
        )
        
        # Perform the sync
        with tqdm(desc="Uploading Tiles", unit="files") as pbar:
            # We construct a simple iterator wrapper to update progress
            # Note: b2sdk sync is complex to hook into for progress bars perfectly,
            # so we run it and let it print its own log or just wait.
            # For simplicity in this script, we just run the sync:
            synchronizer.sync_folders(
                source_folder=source_folder,
                dest_bucket=bucket,
                dest_folder=destination_folder,
                now_millis=int(time.time() * 1000),
                keep_days_or_delete=None,
            )
            
        print("Upload Complete!")

    except Exception as e:
        print(f"B2 Upload Failed: {e}")

# -----------------------------------------------------------------------------
# MATH & GEOMETRY
# -----------------------------------------------------------------------------

@numba.jit(nopython=True)
def haversine_distance_vectorized(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * DEG_TO_RAD
    dlon = (lon2 - lon1) * DEG_TO_RAD
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1 * DEG_TO_RAD) * np.cos(lat2 * DEG_TO_RAD) * np.sin(dlon / 2.0)**2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return EARTH_RADIUS * c

def assign_ski_area(points, max_km=2):
    if not points or not ski_areas_data.get("features"):
        return "Unknown"
    try:
        step = max(1, len(points) // 50)
        sample_points = points[::step]
        line = geom.LineString([(lon, lat) for lat, lon, _ in sample_points])
        centroid = line.centroid
        
        for feature in ski_areas_data["features"]:
            props = feature.get("properties", {})
            if not props: continue
            name = props.get("name")
            if not name: continue

            try:
                geometry = geom.shape(feature["geometry"])
            except Exception: continue

            if geometry.contains(centroid):
                return name

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

        try:
            area_name = assign_ski_area(points)
            avg_lat = sum(p[0] for p in points) / len(points)
            avg_lon = sum(p[1] for p in points) / len(points)
            centroid_coords = (avg_lat, avg_lon)
        except Exception:
            area_name = "Unknown"
            centroid_coords = None

        return (points, 0, area_name, centroid_coords)

    except Exception as e:
        print(f"Error processing {filename}: {str(e)}")
        return ([], 0, "Unknown", None)

# -----------------------------------------------------------------------------
# MAP GENERATION
# -----------------------------------------------------------------------------

def generate_optimized_map(ski_areas_map=None):
    
    mymap = folium.Map(
        location=[47.85, 16.01],
        zoom_start=6,
        max_zoom=19,
        prefer_canvas=True,
        tiles="CartoDB Positron",
        attr='&copy; OSM &copy; CARTO'
    )
    
    LocateControl(auto_start=False, strings={"title": "Show my location"}, position="topright").add_to(mymap)
    
    # --- TILE LAYER CONFIGURATION ---
    import time
    cache_buster = str(int(time.time()))
    
    if USE_REMOTE_TILES:
        # Construct B2 URL: https://f002.../file/bucket/tiles/{z}/{x}/{y}.png
        tile_url = f"{B2_FRIENDLY_URL}tiles/{{z}}/{{x}}/{{y}}.png"
        print(f"Map configured to use remote tiles: {tile_url}")
    else:
        # Use local relative path
        tile_url = f'tiles/{{z}}/{{x}}/{{y}}.png?{cache_buster}'
        print("Map configured to use local tiles.")

    ski_layer = folium.TileLayer(
        tiles=tile_url,
        attr='Ski Tracks',
        name='Ski Tracks',
        min_zoom=10,
        max_zoom=19,
        overlay=True,
        detectRetina=True,
        crossOrigin='anonymous', # Crucial for CORS/B2
        opacity=0.9,
        errorTileUrl='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
    )
    ski_layer.add_to(mymap)
    
    # --- RESORT SELECTOR JS ---
    if ski_areas_map:
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

        var selectorControl = L.control({{position: 'topright'}});
        selectorControl.onAdd = function (map) {{
            var div = L.DomUtil.create('div', 'info legend');
            div.innerHTML = '<select id="area_selector" class="ski-resort-dropdown">{options_html}</select>';
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
                    map.flyTo(skiAreas[val], 13, {{animate: true, duration: 1.5}});
                }}
            }});
        }}
        
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
# MAIN
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate Ski Map & Upload to B2.")
    parser.add_argument('--html-only', action='store_true', help="Skip tile generation, regenerate HTML only")
    parser.add_argument('--upload', action='store_true', help="Upload tiles to Backblaze B2 after generation")
    args = parser.parse_args()
    
    # 1. Rust Tile Generation
    if not args.html_only:
        print("Step 1: Running Rust Renderer...")
        if os.path.exists("ski_renderer.exe"):
            try:
                subprocess.run(["ski_renderer.exe"], check=True)
            except subprocess.CalledProcessError:
                print("Error: Rust renderer failed.")
                sys.exit(1)
        else:
            print("Warning: ski_renderer.exe not found.")

    # 2. Upload to B2 (Optional)
    if args.upload:
        if B2_AVAILABLE:
            sync_tiles_to_b2()
        else:
            print("Cannot upload: b2sdk not installed.")

    # 3. Index Resorts
    print("Step 2: Indexing Resorts...")
    found_ski_areas = defaultdict(list)
    files = [f for f in os.listdir(MERGE_DIRECTORY) if f.endswith('.gpx')]
    
    with ProcessPoolExecutor(max_workers=mp.cpu_count()) as executor:
        futures = {executor.submit(process_gpx_file_optimized, f): f for f in files}
        for future in tqdm(as_completed(futures), total=len(files), desc="Indexing"):
            try:
                _, _, area_name, centroid = future.result()
                if area_name and area_name != "Unknown" and centroid is not None:
                    found_ski_areas[area_name].append(centroid)
            except Exception: continue

    final_area_map = {}
    for name, coords_list in found_ski_areas.items():
        if coords_list:
            avg_lat = sum(c[0] for c in coords_list) / len(coords_list)
            avg_lon = sum(c[1] for c in coords_list) / len(coords_list)
            final_area_map[name] = [avg_lat, avg_lon]

    # 4. Generate HTML
    print("Step 3: Generating HTML...")
    mymap = generate_optimized_map(final_area_map)
    
    # CSS & Analytics
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
    .leaflet-tile { image-rendering: pixelated; }
    .leaflet-container { background: #f0f0f0; }
    
    /* Dropdown Styles */
    .ski-resort-dropdown {
        font-size: 14px;
        padding: 8px;
        border-radius: 4px;
        border: 1px solid #ccc;
        box-shadow: 0 1px 5px rgba(0,0,0,0.4);
        background: white;
        max-width: 300px;
    }
    @media screen and (max-width: 768px) {
        .ski-resort-dropdown {
            font-size: 11px !important;    
            padding: 4px !important;
            max-width: 150px !important;
            height: 30px;
        }
    }
    </style>
    """

    html_content = mymap.get_root().render()
    if "</head>" in html_content:
        injection = google_analytics + custom_css
        html_content = html_content.replace("</head>", injection + "</head>", 1)
        
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print("Done! Map updated.")

if __name__ == "__main__":
    main()