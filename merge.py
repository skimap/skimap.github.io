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
import folium

# ---------------------------
# Konfiguráció
# ---------------------------
merge_directory = "tracks/processed/all"
output_geojson_dir = "tracks_geojson"
min_zoom_level = 14
line_width = 3
max_features_per_file = 2000
mode = "clean"   # "append" vagy "clean"

# processzorok száma (állítható)
num_workers = os.cpu_count() or 4

# Metadata fájlok
chunk_bboxes_file = os.path.join(output_geojson_dir, "chunk_bboxes.json")
ski_areas_file = os.path.join(output_geojson_dir, "ski_areas.json")

# Kimeneti mappa létrehozása
os.makedirs(output_geojson_dir, exist_ok=True)

# Ha clean mód, ürítjük a kimeneti mappát
if mode == "clean":
    for filename in os.listdir(output_geojson_dir):
        file_path = os.path.join(output_geojson_dir, filename)
        if os.path.isfile(file_path) or os.path.islink(file_path):
            os.unlink(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)

# ---------------------------
# Segédadatok betöltése
# ---------------------------
# lifts_e: várható formátum: [[lon, lat], ...] vagy hasonló
try:
    with open('json/lifts/lifts_e.json', encoding='utf-8') as f:
        lifts_e = json.load(f)
except Exception:
    lifts_e = []
# (lat, lon) tuple-ek a geopy használatához
lift_end_coordinate_tuples = [(lift[1], lift[0]) for lift in lifts_e if len(lift) >= 2]

# Ski area geojson betöltése
with open("json/ski_areas/ski_areas.geojson", encoding="utf-8") as f:
    ski_areas_data = json.load(f)

# convenience lista (név, shapely geometry)
ski_areas = []
for feature in ski_areas_data.get("features", []):
    name = feature.get("properties", {}).get("name", "Unknown")
    try:
        shape_obj = geom.shape(feature["geometry"])
        ski_areas.append((name, shape_obj))
    except Exception:
        pass

# ---------------------------
# Ski area persistence
# ---------------------------
def load_saved_ski_areas():
    if os.path.exists(ski_areas_file):
        try:
            with open(ski_areas_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(x) for x in data]
        except Exception as e:
            print(f"Warning: couldn't load saved ski areas: {e}")
    return []

def save_ski_areas(areas_list):
    try:
        with open(ski_areas_file, 'w', encoding='utf-8') as f:
            json.dump(sorted(list(areas_list)), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: couldn't write ski_areas file: {e}")

# ---------------------------
# Ski area assign (centroid / distance / point)
# ---------------------------
def assign_ski_area(points, max_km=2):
    """
    Visszaadja az adott track-hez tartozó síterület nevét (ha található), egyébként "Unknown".
    points: list of (lat, lon, elev)
    """
    if not points:
        return "Unknown"

    try:
        line = geom.LineString([(lon, lat) for lat, lon, _ in points])
    except Exception:
        return "Unknown"

    centroid = line.centroid

    for feature in ski_areas_data.get("features", []):
        name = feature.get("properties", {}).get("name", "Unknown")
        try:
            geometry = geom.shape(feature["geometry"])
        except Exception:
            continue

        # centroid belül van a polygonban?
        try:
            if geometry.contains(centroid):
                return name
        except Exception:
            pass

        # poligonoknál: min geodesic távolság a külső csúcsoktól
        try:
            if hasattr(geometry, "exterior") or getattr(geometry, "geom_type", "") in ("MultiPolygon",):
                polygons = [geometry] if geometry.geom_type == "Polygon" else list(getattr(geometry, "geoms", [geometry]))
                c_latlon = (centroid.y, centroid.x)
                poly_min_dists = []
                for poly in polygons:
                    coords = list(getattr(poly, "exterior").coords) if hasattr(poly, "exterior") else []
                    if not coords:
                        continue
                    vertex_min = min(
                        geo_distance(c_latlon, (coord[1], coord[0])).km
                        for coord in coords
                    )
                    poly_min_dists.append(vertex_min)
                if poly_min_dists and min(poly_min_dists) <= max_km:
                    return name
        except Exception:
            pass

        # pont geometria közelség
        try:
            if geometry.geom_type == "Point":
                if geo_distance((centroid.y, centroid.x), (geometry.y, geometry.x)).km <= max_km:
                    return name
        except Exception:
            pass

    return "Unknown"

# ---------------------------
# get_color (a te megadott logikád, numpy használatával)
# ---------------------------
def get_color(rate: float, coloring_scheme: int):
    # vigyázat: rate lehet NaN/None — kezeljük
    try:
        rate_val = float(rate)
    except Exception:
        rate_val = 0.0

    if coloring_scheme == 1:
        if rate_val >= 0:
            return '#80808020'
        elif rate_val >= -0.15:
            return 'green'
        elif rate_val >= -0.29:
            return 'blue'
        elif rate_val >= -0.45:
            return 'red'
        else:
            return 'black'
    if coloring_scheme == 2:
        if rate_val >= 0:
            return '#80808080'
        elif rate_val >= -0.07:
            return '#48B748'    # light green
        elif rate_val >= -0.15:
            return '#006400'    # dark green
        elif rate_val >= -0.20:
            return '#32A2D9'    # light blue
        elif rate_val >= -0.25:
            return '#0000FF'    # blue
        elif rate_val >= -0.3:
            return '#800080'    # purple
        elif rate_val >= -0.37:
            return 'red'
        elif rate_val >= -0.45:
            return 'darkred'
        else:
            return 'black'
    if coloring_scheme == 3:    # 100% is 56°, European colors
        # alpha: mapping from rate (tangent) to degrees
        alpha = np.arctan(rate_val) * 2 / np.pi * 90
        ski_slope_rate = alpha / 56
        if ski_slope_rate >= 0:
            return '#80808080'
        elif ski_slope_rate >= -0.07:
            return '#48B748'
        elif ski_slope_rate >= -0.15:
            return '#006400'
        elif ski_slope_rate >= -0.20:
            return '#32A2D9'
        elif ski_slope_rate >= -0.25:
            return '#0000FF'
        elif ski_slope_rate >= -0.3:
            return '#800080'
        elif ski_slope_rate >= -0.37:
            return 'red'
        elif ski_slope_rate >= -0.45:
            return 'darkred'
        else:
            return 'black'
    if coloring_scheme == 4:    # 100% is 45°, Hungarian colors
        alpha = np.arctan(rate_val) * 2 / np.pi * 90
        ski_slope_rate = alpha / 45
        if ski_slope_rate >= 0:
            return '#80808080'
        elif ski_slope_rate >= -0.07:
            return '#48B748'
        elif ski_slope_rate >= -0.15:
            return '#006400'
        elif ski_slope_rate >= -0.20:
            return '#32A2D9'
        elif ski_slope_rate >= -0.25:
            return '#0000FF'
        elif ski_slope_rate >= -0.3:
            return '#800080'
        elif ski_slope_rate >= -0.37:
            return 'red'
        elif ski_slope_rate >= -0.45:
            return 'darkred'
        else:
            return 'black'
    # default
    return '#888888'

# ---------------------------
# Egy GPX fájl feldolgozása
# ---------------------------
def process_gpx_file(filename):
    """
    Visszatér: (segments, skiing_count, centroid_coords)
    segments: list of (colors_dict, [(lat,lon),(lat,lon)], ski_area_name)
    colors_dict: {"scheme1": "#...", "scheme2": "...", ...}
    """
    try:
        file_path = os.path.join(merge_directory, filename)
        with open(file_path, 'r', encoding='utf-8') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for p in segment.points:
                    points.append((p.latitude, p.longitude, p.elevation if p.elevation is not None else 0.0))

        if len(points) < 2:
            return ([], 0, None)

        # ski area
        ski_area_name = assign_ski_area(points)

        # centroid coords
        line = geom.LineString([(lon, lat) for lat, lon, _ in points])
        centroid = line.centroid
        centroid_coords = (centroid.y, centroid.x)

        # descent rates: elevation diff / horizontal distance (meters)
        descent_rates = []
        for i in range(1, len(points)):
            h_dist = gpxpy.geo.haversine_distance(
                points[i-1][0], points[i-1][1],
                points[i][0], points[i][1]
            )  # meters
            elevation_gain = points[i][2] - points[i-1][2]
            descent_rates.append(elevation_gain / h_dist if h_dist != 0 else 0.0)

        # moving average window (window = 5). At start use shorter window properly.
        window = 5
        moving_avg = []
        for i in range(len(descent_rates)):
            start = max(0, i - (window - 1))
            window_vals = descent_rates[start:i+1]
            moving_avg.append(sum(window_vals) / len(window_vals))

        segments = []
        skiing = 0

        for i in range(len(points) - 1):
            if i >= len(moving_avg):
                break

            current_point = (points[i][0], points[i][1])  # (lat, lon)
            next_point = (points[i+1][0], points[i+1][1])

            val = moving_avg[i]

            # compute all 4 scheme colors using Python get_color
            scheme_colors = {
                "scheme1": get_color(val, 1),
                "scheme2": get_color(val, 2),
                "scheme3": get_color(val, 3),
                "scheme4": get_color(val, 4),
            }

            # optional skiing detection (idéző logika megtartva: ha korábban pozitív volt majd hirtelen negatív és közel lift)
            try:
                if i >= 5 and all(m >= 0 for m in moving_avg[max(0, i-5):i]) and moving_avg[i] < 0:
                    # proximity to lifts (<50 m)
                    if any(gpxpy.geo.haversine_distance(current_point[0], current_point[1], lift[0], lift[1]) < 50 for lift in lift_end_coordinate_tuples):
                        skiing += 1
            except Exception:
                pass

            segments.append((scheme_colors, [current_point, next_point], ski_area_name))

        return (segments, skiing, centroid_coords)
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return ([], 0, None)

# ---------------------------
# GeoJSON chunkok generálása + chunk_bboxes.json
# ---------------------------
def generate_geojson(all_segments):
    features = []
    for idx, (colors, segment, ski_area) in enumerate(all_segments):
        if len(segment) < 2:
            continue
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lat, lon in segment]
            },
            "properties": {
                "scheme1": colors.get("scheme1"),
                "scheme2": colors.get("scheme2"),
                "scheme3": colors.get("scheme3"),
                "scheme4": colors.get("scheme4"),
                "ski_area": ski_area,
                "min_zoom": min_zoom_level,
                "z_index": idx
            }
        })

    # load existing chunk_bboxes if append
    if mode == "append" and os.path.exists(chunk_bboxes_file):
        try:
            with open(chunk_bboxes_file, 'r', encoding='utf-8') as f:
                chunk_bboxes = json.load(f)
        except Exception:
            chunk_bboxes = {}
    else:
        chunk_bboxes = {}

    # determine start index
    existing_indices = []
    for fname in chunk_bboxes.keys():
        if fname.startswith("tracks_") and fname.endswith(".geojson"):
            try:
                existing_indices.append(int(fname.replace("tracks_", "").replace(".geojson", "")))
            except Exception:
                pass
    start_index = max(existing_indices) + 1 if existing_indices else 0

    file_paths = []
    num_files = math.ceil(len(features) / max_features_per_file) if features else 0

    for i in range(num_files):
        start_idx = i * max_features_per_file
        end_idx = min((i + 1) * max_features_per_file, len(features))
        chunk = features[start_idx:end_idx]

        all_coords = []
        for feature in chunk:
            coords = feature['geometry']['coordinates']
            all_coords.extend(coords)

        if all_coords:
            lons = [c[0] for c in all_coords]
            lats = [c[1] for c in all_coords]
            bbox = [min(lons), min(lats), max(lons), max(lats)]
        else:
            bbox = [0, 0, 0, 0]

        file_index = start_index + i
        geojson_basename = f"tracks_{file_index}.geojson"
        geojson_path = os.path.join(output_geojson_dir, geojson_basename)
        try:
            with open(geojson_path, 'w', encoding='utf-8') as f:
                json.dump({"type": "FeatureCollection", "features": chunk}, f, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: could not write {geojson_path}: {e}")
            continue

        file_paths.append(geojson_path)
        chunk_bboxes[geojson_basename] = bbox

    # save chunk_bboxes
    try:
        with open(chunk_bboxes_file, 'w', encoding='utf-8') as f:
            json.dump(chunk_bboxes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: couldn't write chunk_bboxes.json: {e}")

    return file_paths

# ---------------------------
# Folium térkép generálása (JS-sel: sémaváltás, lazy load)
# ---------------------------
def generate_map(geojson_paths, centroids, initial_available_areas):
    mymap = folium.Map(
        location=[47.85, 16.01],
        zoom_start=6,
        max_zoom=19,
        prefer_canvas=True,
        tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attr='Map data © OpenStreetMap contributors'
    )

    LocateControl(
        auto_start=False,
        strings={"title": "Show my location"},
        position="topright",
        locate_options={"enableHighAccuracy": True}
    ).add_to(mymap)

    selector_html = """
    <div id="ski-selector" style="position:absolute;top:10px;right:50px;z-index:1000;background:white;padding:5px;border-radius:8px;">
        <label for="area">Síterep:</label>
        <select id="area">
            <option value="all">Minden</option>
        </select>
    </div>
    <div id="scheme-selector" style="position:absolute;top:80px;right:50px;z-index:1000;background:white;padding:5px;border-radius:8px;">
        <label for="scheme">Pályaszínek:</label>
        <select id="scheme">
            <option value="3">EU</option>
            <option value="4">HU</option>
        </select>
    </div>
    """
    mymap.get_root().html.add_child(folium.Element(selector_html))

    # Build ski area polygons mapping for JS (only those in initial_available_areas)
    ski_area_polygons = {}
    for feat in ski_areas_data.get("features", []):
        name = feat.get("properties", {}).get("name", "Unknown")
        if name in initial_available_areas:
            ski_area_polygons[name] = feat.get("geometry")

    ski_area_js = json.dumps(ski_area_polygons, ensure_ascii=False)
    initial_available_areas_js = json.dumps(initial_available_areas, ensure_ascii=False)

    # JS script (lazy load chunk geojsons, selector, scheme switch)
    script = f"""
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        const map = window['{mymap.get_name()}'];
        const MIN_ZOOM = {min_zoom_level};
        const lineWidth = {line_width};
        let loadedFiles = new Set();
        let lastUpdate = 0;
        const UPDATE_INTERVAL = 100;
        const MAX_LOAD_DISTANCE = 0.2;
        const skiAreas = {ski_area_js};
        const initialAvailableAreas = {initial_available_areas_js};
        const trackLayerGroup = L.layerGroup().addTo(map);
        let availableAreas = new Set(initialAvailableAreas);
        let currentScheme = 1;

        function populateSelectorInitial() {{
            const selector = document.getElementById("area");
            const existing = new Set(Array.from(selector.options).map(o => o.value));
            initialAvailableAreas.forEach(area => {{
                if (!existing.has(area)) {{
                    const opt = document.createElement("option");
                    opt.value = area;
                    opt.textContent = area;
                    selector.appendChild(opt);
                }}
            }});
        }}
        populateSelectorInitial();

        async function loadGeoJSON(path) {{
            if (loadedFiles.has(path)) return;
            try {{
                const response = await fetch(path);
                const data = await response.json();
                data.features.forEach(f => {{
                    if (f && f.properties && f.properties.ski_area) {{
                        availableAreas.add(f.properties.ski_area);
                    }}
                }});
                updateSelectorFromSet();

                const layer = L.geoJSON(data, {{
                    filter: function(feature) {{
                        const selectedArea = document.getElementById("area").value;
                        return selectedArea === "all" || feature.properties.ski_area === selectedArea;
                    }},
                    style: function(feature) {{
                        // take the precomputed scheme color from properties
                        const color = feature.properties["scheme" + currentScheme];
                        return {{
                            color: color,
                            weight: lineWidth,
                            opacity: map.getZoom() >= MIN_ZOOM ? 1 : 0,
                            zIndex: feature.properties.z_index
                        }};
                    }},
                    interactive: false,
                    pmIgnore: true,
                    renderer: L.canvas({{ padding: 0.5 }}),
                }});
                layer.addTo(trackLayerGroup);
                loadedFiles.add(path);
            }} catch (error) {{
                console.error('Failed to load track file:', path, error);
            }}
        }}

        function updateSelectorFromSet() {{
            const selector = document.getElementById("area");
            const existing = new Set(Array.from(selector.options).map(o => o.value));
            Array.from(availableAreas).sort().forEach(area => {{
                if (!existing.has(area)) {{
                    const opt = document.createElement("option");
                    opt.value = area;
                    opt.textContent = area;
                    selector.appendChild(opt);
                }}
            }});
        }}

        document.getElementById("scheme").addEventListener("change", function() {{
            currentScheme = parseInt(this.value) || 1;
            trackLayerGroup.clearLayers();
            loadedFiles.clear();
            updateVisibility();
        }});

        document.getElementById("area").addEventListener("change", function() {{
            trackLayerGroup.clearLayers();
            loadedFiles.clear();
            updateVisibility();
            const selectedArea = this.value;
            if (selectedArea !== "all" && skiAreas[selectedArea]) {{
                const layer = L.geoJSON(skiAreas[selectedArea]);
                try {{
                    const bounds = layer.getBounds();
                    if (bounds && bounds.isValid()) {{
                        map.fitBounds(bounds, {{ maxZoom: MIN_ZOOM }});
                        if (map.getZoom() < MIN_ZOOM) map.setZoom(MIN_ZOOM);
                    }}
                }} catch (e) {{
                    console.warn('Could not fit bounds for selected area:', e);
                }}
            }}
        }});

        async function getFeaturesInView() {{
            if (map.getZoom() < MIN_ZOOM) return [];
            const bounds = map.getBounds();
            try {{
                const response = await fetch('tracks_geojson/chunk_bboxes.json');
                const chunkBBoxes = await response.json();
                const expandedBounds = L.latLngBounds(
                    [bounds.getSouth() - MAX_LOAD_DISTANCE, bounds.getWest() - MAX_LOAD_DISTANCE],
                    [bounds.getNorth() + MAX_LOAD_DISTANCE, bounds.getEast() + MAX_LOAD_DISTANCE]
                );
                const filesToLoad = [];
                for (const [file, bbox] of Object.entries(chunkBBoxes)) {{
                    const chunkBounds = L.latLngBounds([bbox[1], bbox[0]], [bbox[3], bbox[2]]);
                    if (expandedBounds.overlaps(chunkBounds)) {{
                        filesToLoad.push(file);
                    }}
                }}
                return filesToLoad;
            }} catch (error) {{
                console.error('Error loading chunk_bboxes.json:', error);
                return [];
            }}
        }}

        async function loadVisibleFeatures() {{
            if (map.getZoom() < MIN_ZOOM) return;
            const filesToLoad = await getFeaturesInView();
            const loadPromises = filesToLoad.map(path => loadGeoJSON(`tracks_geojson/${{path}}`));
            await Promise.all(loadPromises);
        }}

        function throttledUpdateVisibility() {{
            const now = Date.now();
            if (now - lastUpdate > UPDATE_INTERVAL) {{
                updateVisibility();
                lastUpdate = now;
            }}
        }}

        function updateVisibility() {{
            const currentZoom = map.getZoom();
            const shouldShow = currentZoom >= MIN_ZOOM;
            trackLayerGroup.eachLayer(layer => {{
                layer.eachLayer(featureLayer => {{
                    if (featureLayer.setStyle) {{
                        featureLayer.setStyle({{ opacity: shouldShow ? 1 : 0 }});
                    }}
                }});
            }});
            if (shouldShow) loadVisibleFeatures();
        }}

        map.whenReady(function() {{
            if (map.getZoom() >= MIN_ZOOM) loadVisibleFeatures();
            map.on('zoomend', throttledUpdateVisibility);
            map.on('moveend', throttledUpdateVisibility);
            updateVisibility();
        }});
    }});
    </script>
    """

    mymap.get_root().html.add_child(folium.Element(script))
    return mymap

# ---------------------------
# Main
# ---------------------------
def main():
    all_segments = []
    total_skiing = 0
    centroids = []

    # GPX fájlok listázása
    files = [f for f in os.listdir(merge_directory) if f.endswith(".gpx")]
    if not files:
        print("No GPX files found in", merge_directory)
        return

    print(f"Processing {len(files)} GPX files with {num_workers} worker(s)...")
    futures = {}
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for filename in files:
            futures[executor.submit(process_gpx_file, filename)] = filename

        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing tracks"):
            filename = futures[future]
            try:
                segments, skiing, centroid = future.result()
                all_segments.extend(segments)
                total_skiing += skiing
                if centroid:
                    centroids.append({"coords": centroid})
            except Exception as e:
                print(f"Error processing {filename}: {e}")

    # used ski areas (exclude Unknown)
    used_ski_areas = sorted({ski_area for (_, _, ski_area) in all_segments if ski_area and ski_area != "Unknown"})

    # load stored areas if append
    stored_areas = load_saved_ski_areas() if mode == "append" else []
    merged_areas = sorted(set(stored_areas) | set(used_ski_areas))

    # save merged list
    save_ski_areas(merged_areas)

    # generate geojson chunkok
    geojson_paths = generate_geojson(all_segments)

    # generate map & write index.html
    mymap = generate_map(geojson_paths, centroids, merged_areas)

    google_analytics = """
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-HLZTNBRD6S"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments)}
      gtag('js', new Date());
      gtag('config', 'G-HLZTNBRD6S');
    </script>
    """

    html_content = mymap.get_root().render()
    if "</head>" in html_content:
        html_content = html_content.replace("</head>", google_analytics + "</head>", 1)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nTotal skiing segments detected: {total_skiing}")
    print(f"Generated {len(geojson_paths)} GeoJSON files")
    print("Map generated: index.html")
    print(f"Saved ski areas to: {ski_areas_file}")
    print(f"Saved chunk bboxes to: {chunk_bboxes_file}")

if __name__ == "__main__":
    main()
