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

# --- Load Environment Variables ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- B2 SDK Import ---
B2_AVAILABLE = False
try:
    from b2sdk.v2 import InMemoryAccountInfo, B2Api, LocalFolder, B2Folder, Synchronizer, SyncReport
    B2_AVAILABLE = True
except ImportError:
    pass

try:
    import color as c
except ImportError:
    pass

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
MERGE_DIRECTORY = "tracks/raw/all"
OUTPUT_GEOJSON_DIR = "tracks_geojson"
TILES_OUTPUT_DIR = "frontend/public/tiles"
SKI_AREAS_FILE = "json/ski_areas/ski_areas.geojson"
LIFTS_FILE = "json/lifts/lifts_e.json"

# Asset Paths
MAP_LOGIC_JS = "assets/map_logic.js"
MAP_STYLES_CSS = "assets/map_styles.css"

# --- BACKBLAZE B2 CONFIGURATION ---
B2_KEY_ID = os.getenv("B2_KEY_ID")
B2_APP_KEY = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
B2_FRIENDLY_URL = os.getenv("B2_FRIENDLY_URL")

USE_REMOTE_TILES = bool(B2_FRIENDLY_URL)

EARTH_RADIUS = 6371000
DEG_TO_RAD = math.pi / 180.0

# -----------------------------------------------------------------------------
# B2 OPERATIONS
# -----------------------------------------------------------------------------

def get_b2_api():
    """Helper to authenticate and return B2 API and Bucket."""
    if not B2_AVAILABLE or not B2_KEY_ID or not B2_APP_KEY:
        return None, None
    try:
        info = InMemoryAccountInfo()
        b2_api = B2Api(info)
        b2_api.authorize_account("production", B2_KEY_ID, B2_APP_KEY)
        bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)
        return b2_api, bucket
    except Exception as e:
        print(f"B2 Auth Error: {e}")
        return None, None

def configure_cors():
    """Sets CORS rules on the B2 bucket to allow browser access."""
    print("Checking B2 CORS permissions...")
    b2_api, bucket = get_b2_api()
    if not bucket:
        print("Skipping CORS config (No Auth).")
        return

    try:
        cors_rules = [
            {
                "corsRuleName": "allowAny",
                "allowedOrigins": ["*"],
                "allowedOperations": ["GET", "HEAD"],
                "allowedHeaders": ["*"],
                "maxAgeSeconds": 3600
            }
        ]
        bucket.update(cors_rules=cors_rules)
        print("✅ CORS rules updated! Map tiles are now public.")
    except Exception as e:
        print(f"⚠️ Warning: Could not configure CORS: {e}")

def sync_tiles_to_b2():
    print("\n--- Starting B2 Sync ---")
    b2_api, _ = get_b2_api()
    if not b2_api:
        print("Cannot sync: B2 Auth failed or keys missing.")
        return

    try:
        source_path = os.path.abspath(TILES_OUTPUT_DIR)
        destination_path_in_bucket = "tiles" 

        source_folder = LocalFolder(source_path)
        dest_folder = B2Folder(B2_BUCKET_NAME, destination_path_in_bucket, b2_api)

        print(f"Syncing local {source_path} -> B2:/{destination_path_in_bucket}...")
        
        synchronizer = Synchronizer(max_workers=20, dry_run=False)
        reporter = SyncReport(sys.stdout, no_progress=False)
        
        synchronizer.sync_folders(
            source_folder=source_folder,
            dest_folder=dest_folder,
            now_millis=int(time.time() * 1000),
            reporter=reporter, 
        )
        print("\n✅ Tile Sync Complete!")

    except Exception as e:
        print(f"\n❌ B2 Sync Error: {e}")

# -----------------------------------------------------------------------------
# HELPERS & PROCESSING
# -----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_lift_data():
    try:
        with open(LIFTS_FILE) as f: return [(x[1], x[0]) for x in json.load(f)]
    except FileNotFoundError: return []

@lru_cache(maxsize=1)
def load_ski_areas_data():
    try:
        with open(SKI_AREAS_FILE, encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return {"features": []}

lift_end_coordinate_tuples = load_lift_data()
ski_areas_data = load_ski_areas_data()

@numba.jit(nopython=True)
def haversine_distance_vectorized(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * DEG_TO_RAD
    dlon = (lon2 - lon1) * DEG_TO_RAD
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1 * DEG_TO_RAD) * np.cos(lat2 * DEG_TO_RAD) * np.sin(dlon / 2.0)**2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return EARTH_RADIUS * c

def assign_ski_area(points, max_km=2):
    if not points or not ski_areas_data.get("features"): return "Unknown"
    try:
        step = max(1, len(points) // 50)
        sample_points = points[::step]
        line = geom.LineString([(lon, lat) for lat, lon, _ in sample_points])
        centroid = line.centroid
        for feature in ski_areas_data["features"]:
            props = feature.get("properties", {})
            if not props or not props.get("name"): continue
            try: geometry = geom.shape(feature["geometry"])
            except: continue
            if geometry.contains(centroid): return props.get("name")
            feature_center = geometry.centroid
            dist = geo_distance((centroid.y, centroid.x), (feature_center.y, feature_center.x)).km
            if dist < max_km: return props.get("name")
    except: pass
    return "Unknown"

def process_gpx_file_optimized(filename):
    filepath = os.path.join(MERGE_DIRECTORY, filename)
    try:
        with open(filepath, 'r') as f: gpx = gpxpy.parse(f)
        points = []
        for t in gpx.tracks:
            for s in t.segments:
                for p in s.points: points.append((p.latitude, p.longitude, p.elevation))
        if len(points) < 2: return ([], 0, "Unknown", None)
        area_name = assign_ski_area(points)
        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lon = sum(p[1] for p in points) / len(points)
        return (points, 0, area_name, (avg_lat, avg_lon))
    except Exception as e:
        print(f"Error {filename}: {e}")
        return ([], 0, "Unknown", None)

def generate_optimized_map(ski_areas_map=None):
    mymap = folium.Map(location=[47.85, 16.01], zoom_start=6, max_zoom=19, prefer_canvas=True, tiles="CartoDB Positron")
    LocateControl(auto_start=False, strings={"title": "Show my location"}, position="topright").add_to(mymap)
    
    if USE_REMOTE_TILES and B2_FRIENDLY_URL:
        base_url = B2_FRIENDLY_URL if B2_FRIENDLY_URL.endswith('/') else B2_FRIENDLY_URL + '/'
        tile_url = f"{base_url}tiles/{{z}}/{{x}}/{{y}}.png"
        print(f"Using Remote Tiles: {tile_url}")
    else:
        tile_url = 'tiles/{z}/{x}/{y}.png'
        print("Using Local Tiles.")

    ski_layer = folium.TileLayer(
        tiles=tile_url, attr='Ski Tracks', name='Ski Tracks', min_zoom=6, max_zoom=19, overlay=True,
        detectRetina=True, crossOrigin='anonymous', opacity=0.9,
        # We use a transparent 1x1 pixel here as a fallback
        errorTileUrl='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
    )
    ski_layer.add_to(mymap)
    
    areas_js = json.dumps(ski_areas_map or {})
    
    # Read external JS logic
    with open(MAP_LOGIC_JS, "r") as f:
        js_logic = f.read()

    macro = MacroElement()
    macro._template = Template(f"""
    {{% macro script(this, kwargs) %}}
        {js_logic}
        
        // Initialize with data from Python
        initMapControls({mymap.get_name()}, {ski_layer.get_name()}, {areas_js});
    {{% endmacro %}}
    """)
    
    mymap.get_root().add_child(macro)
    return mymap

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--html-only', action='store_true', help="Skip tile generation")
    parser.add_argument('--update-tiles', action='store_true', help="Upload tiles to B2")
    args = parser.parse_args()

    # 2. GENERATE TILES (Run Rust Renderer)
    if not args.html_only:
        print("Step 1: Generating Tiles (ski_renderer.exe)...")
        if os.path.exists("ski_renderer.exe"):
            try: subprocess.run(["ski_renderer.exe"], check=True)
            except: sys.exit("Error: Rust renderer failed.")
        else: print("Warning: ski_renderer.exe missing.")
    
    # 3. UPLOAD TILES
    if args.update_tiles:
        sync_tiles_to_b2()

    # 4. GENERATE DATA FOR FRONTEND
    print("Step 2: Indexing Resorts...")
    with ProcessPoolExecutor(max_workers=mp.cpu_count()) as ex:
        files = [f for f in os.listdir(MERGE_DIRECTORY) if f.endswith('.gpx')]
        resorts = defaultdict(list)
        for fut in tqdm(as_completed([ex.submit(process_gpx_file_optimized, f) for f in files]), total=len(files)):
            _, _, name, center = fut.result()
            if name != "Unknown" and center: resorts[name].append(center)
    
    final_map = {k: [sum(x[0] for x in v)/len(v), sum(x[1] for x in v)/len(v)] for k, v in resorts.items()}
    print(f"Found {len(final_map)} ski areas.")
    
    # Determine Tile URL
    if USE_REMOTE_TILES and B2_FRIENDLY_URL:
        base_url = B2_FRIENDLY_URL if B2_FRIENDLY_URL.endswith('/') else B2_FRIENDLY_URL + '/'
        tile_url = f"{base_url}tiles/{{z}}/{{x}}/{{y}}.png"
        print(f"Using Remote Tiles: {tile_url}")
    else:
        # In development, we might serve tiles locally. 
        # Since the React app runs on port 5173 and python server on 8000, 
        # we might need to point to the python server or just use relative if we build into the root.
        # For now, let's assume relative to the public root or a specific absolute path.
        # If we run 'vite' in 'frontend', it serves 'public'. 
        # We need to symlink 'tiles' to 'frontend/public/tiles' or similar for dev.
        tile_url = '/tiles/{z}/{x}/{y}.png' 
        print("Using Local Tiles.")

    data_output = {
        "ski_areas": final_map,
        "tile_url": tile_url
    }
    
    output_path = os.path.join("frontend", "public", "map_data.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data_output, f, indent=2)
        
    print(f"Done! Data written to {output_path}")

if __name__ == "__main__":
    mp.freeze_support()
    main()
