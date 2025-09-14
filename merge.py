import os
import shutil
import json
import math
import folium
import gpxpy
from collections import defaultdict
import color as c
from tqdm import tqdm
from folium.plugins import LocateControl
import shapely.geometry as geom
from geopy.distance import distance as geo_distance
from concurrent.futures import ProcessPoolExecutor, as_completed

# ---------------------------
# Configuration
# ---------------------------
merge_directory = "tracks/processed/all"
coloring_scheme = 4
output_geojson_dir = "tracks_geojson"
min_zoom_level = 14
line_width = 3
max_features_per_file = 2000
mode = "clean"   # "append" vagy "clean" (alapértelmezett: "append")

# Paths for metadata files
chunk_bboxes_file = os.path.join(output_geojson_dir, "chunk_bboxes.json")
ski_areas_file = os.path.join(output_geojson_dir, "ski_areas.json")

# Ensure output dir exists
os.makedirs(output_geojson_dir, exist_ok=True)

# If clean mode, remove all files/subdirs from output dir (restores original behaviour)
if mode == "clean":
    for filename in os.listdir(output_geojson_dir):
        file_path = os.path.join(output_geojson_dir, filename)
        if os.path.isfile(file_path) or os.path.islink(file_path):
            os.unlink(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)

# ---------------------------
# Load auxiliary data
# ---------------------------
# lifts_e: expected list of [lat, lon] or similar in json/lifts/lifts_e.json
with open('json/lifts/lifts_e.json', encoding='utf-8') as f:
    lifts_e = json.load(f)

# keep coordinates as tuples in (lat, lon) order for distance checks
# if original stored as [lon, lat] this swap still works; keep previous approach:
lift_end_coordinate_tuples = [(lift[1], lift[0]) for lift in lifts_e]

# Load ski area polygons (used for assign_ski_area and for zooming in JS)
with open("json/ski_areas/ski_areas.geojson", encoding="utf-8") as f:
    ski_areas_data = json.load(f)

# build convenience list of (name, shapely geometry)
ski_areas = []
for feature in ski_areas_data.get("features", []):
    name = feature.get("properties", {}).get("name", "Unknown")
    try:
        shape_obj = geom.shape(feature["geometry"])
        ski_areas.append((name, shape_obj))
    except Exception:
        # ignore invalid geometry
        pass

# ---------------------------
# Helper: ski area persistence
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
# Assign ski area function (centroid / distance to polygon exterior / point)
# ---------------------------
def assign_ski_area(points, max_km=2):
    """
    Assign ski area name based on centroid of the track.
    Returns a string ski area name (or "Unknown").
    """
    if not points:
        return "Unknown"

    # line: shapely expects (x, y) -> (lon, lat)
    line = geom.LineString([(lon, lat) for lat, lon, _ in points])
    centroid = line.centroid  # shapely Point

    for feature in ski_areas_data.get("features", []):
        name = feature.get("properties", {}).get("name", "Unknown")
        try:
            geometry = geom.shape(feature["geometry"])
        except Exception:
            continue

        # If centroid is inside geometry → match
        try:
            if geometry.contains(centroid):
                return name
        except Exception:
            pass

        # Polygons: check min geodesic distance from centroid to polygon exterior vertices
        try:
            if hasattr(geometry, "exterior") or getattr(geometry, "geom_type", "") in ("MultiPolygon",):
                # normalize to list of polygons
                polygons = [geometry] if geometry.geom_type == "Polygon" else list(getattr(geometry, "geoms", [geometry]))
                poly_min_dists = []
                c_latlon = (centroid.y, centroid.x)  # (lat, lon)
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

        # Point geometry direct check
        try:
            if geometry.geom_type == "Point":
                if geo_distance((centroid.y, centroid.x), (geometry.y, geometry.x)).km <= max_km:
                    return name
        except Exception:
            pass

    return "Unknown"

# ---------------------------
# Process single GPX file: parse, build segments, detect skiing segments
# ---------------------------
def process_gpx_file(filename):
    try:
        file_path = os.path.join(merge_directory, filename)
        with open(file_path, 'r', encoding='utf-8') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        points = []
        for track in gpx.tracks:
            for segment in track.segments:
                # store (lat, lon, elevation)
                points.extend([(p.latitude, p.longitude, p.elevation if p.elevation is not None else 0) for p in segment.points])

        if len(points) < 2:
            return ([], 0, None)

        # assign ski area once per track
        ski_area_name = assign_ski_area(points)

        # centroid coords for possible use
        line = geom.LineString([(lon, lat) for lat, lon, _ in points])
        centroid = line.centroid
        centroid_coords = (centroid.y, centroid.x)

        # descent rates between consecutive points (elevation change / horizontal distance)
        descent_rates = []
        for i in range(1, len(points)):
            h_dist = gpxpy.geo.haversine_distance(
                points[i-1][0], points[i-1][1],
                points[i][0], points[i][1]
            )
            elevation_gain = points[i][2] - points[i-1][2]
            descent_rates.append(elevation_gain / h_dist if h_dist != 0 else 0)

        # moving average (window = 5)
        window = 5
        moving_avg = []
        for i in range(len(descent_rates)):
            start = max(0, i - (window - 1))
            window_vals = descent_rates[start:i+1]
            moving_avg.append(sum(window_vals) / window)

        segments = []
        skiing = 0

        for i in range(len(points) - 1):
            if i >= len(moving_avg):
                break

            current_point = (points[i][0], points[i][1])   # (lat, lon)
            next_point = (points[i+1][0], points[i+1][1])

            # Determine color for this segment
            if i >= 5 and all(m >= 0 for m in moving_avg[max(0, i-5):i]) and moving_avg[i] < 0:
                # check proximity to lifts (<50 m)
                if any(gpxpy.geo.haversine_distance(*current_point, *lift) < 50 for lift in lift_end_coordinate_tuples):
                    color = "#4a412a"
                    skiing += 1
                else:
                    color = c.get_color(moving_avg[i], coloring_scheme)
            else:
                color = c.get_color(moving_avg[i], coloring_scheme)

            # append segment as ((lat,lon), (lat,lon))
            segments.append((color, [current_point, next_point], ski_area_name))

        return (segments, skiing, centroid_coords)
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return ([], 0, None)

# ---------------------------
# Generate GeoJSON chunk files and chunk_bboxes.json
# ---------------------------
def generate_geojson(all_segments):
    features = []
    # Build features list
    for idx, (color, segment, ski_area) in enumerate(all_segments):
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
                "ski_area": ski_area,
                "min_zoom": min_zoom_level,
                "z_index": idx
            }
        })

    # Load existing chunk_bboxes if append
    if mode == "append" and os.path.exists(chunk_bboxes_file):
        try:
            with open(chunk_bboxes_file, 'r', encoding='utf-8') as f:
                chunk_bboxes = json.load(f)
        except Exception:
            chunk_bboxes = {}
    else:
        chunk_bboxes = {}

    # Determine start index based on existing chunk files
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
            min_lon, min_lat = min(lons), min(lats)
            max_lon, max_lat = max(lons), max(lats)
            bbox = [min_lon, min_lat, max_lon, max_lat]
        else:
            bbox = [0, 0, 0, 0]

        file_index = start_index + i
        geojson_basename = f"tracks_{file_index}.geojson"
        geojson_path = os.path.join(output_geojson_dir, geojson_basename)
        with open(geojson_path, 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": chunk}, f, ensure_ascii=False)

        file_paths.append(geojson_path)
        chunk_bboxes[geojson_basename] = bbox

    # Save merged chunk_bboxes back to disk
    try:
        with open(chunk_bboxes_file, 'w', encoding='utf-8') as f:
            json.dump(chunk_bboxes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: couldn't write chunk_bboxes.json: {e}")

    return file_paths

# ---------------------------
# Generate folium map (JS script embedded handles async loading + selector)
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

    # Locate control
    LocateControl(
        auto_start=False,
        strings={"title": "Show my location"},
        position="topright",
        locate_options={"enableHighAccuracy": True}
    ).add_to(mymap)

    # Selector UI
    selector_html = """
    <div id="ski-selector" style="position:absolute;top:10px;right:50px;z-index:1000;background:white;padding:5px;border-radius:8px;">
        <label for="area">Ski Area:</label>
        <select id="area">
            <option value="all">All</option>
        </select>
    </div>
    """
    mymap.get_root().html.add_child(folium.Element(selector_html))

    # Build a mapping name -> geometry for ski areas that we have polygons for
    ski_area_polygons = {}
    for feat in ski_areas_data.get("features", []):
        name = feat.get("properties", {}).get("name", "Unknown")
        if name in initial_available_areas:
            ski_area_polygons[name] = feat.get("geometry")

    ski_area_js = json.dumps(ski_area_polygons, ensure_ascii=False)
    initial_available_areas_js = json.dumps(initial_available_areas, ensure_ascii=False)

    # JS script (handles loading tracks_geojson/*.geojson on demand, populating selector, zooming)
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
                        return {{
                            color: feature.properties.color,
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
                console.log(`Loaded: ${{path}}`);
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

        document.getElementById("area").addEventListener("change", function() {{
            const selectedArea = this.value;
            trackLayerGroup.clearLayers();
            loadedFiles.clear();
            updateVisibility();

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
                    const chunkBounds = L.latLngBounds(
                        [bbox[1], bbox[0]],
                        [bbox[3], bbox[2]]
                    );
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
            const loadPromises = filesToLoad.map(path =>
                loadGeoJSON(`tracks_geojson/${{path}}`)
            );
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

            if (shouldShow) {{
                loadVisibleFeatures();
            }}
        }}

        map.whenReady(function() {{
            if (map.getZoom() >= MIN_ZOOM) {{
                loadVisibleFeatures();
            }}
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

    # collect GPX files
    files = [f for f in os.listdir(merge_directory) if f.endswith(".gpx")]

    # Number of worker processes (set manually or use all cores)
    num_workers = os.cpu_count() or 4  

    # Use ProcessPoolExecutor for parallel CPU work
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_gpx_file, filename): filename for filename in files}

        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing tracks"):
            try:
                segments, skiing, centroid = future.result()
                all_segments.extend(segments)
                total_skiing += skiing
                if centroid:
                    centroids.append({"coords": centroid})
            except Exception as e:
                print(f"Error in {futures[future]}: {e}")

    # used ski areas from this run (exclude Unknown)
    used_ski_areas = sorted({ski_area for (_, _, ski_area) in all_segments if ski_area and ski_area != "Unknown"})

    # load previously saved areas in append mode
    stored_areas = load_saved_ski_areas() if mode == "append" else []
    merged_areas = sorted(set(stored_areas) | set(used_ski_areas))

    # save merged list (overwrites in both modes, so clean will create new file with current areas)
    save_ski_areas(merged_areas)

    # generate geojson chunks & chunk_bboxes.json
    geojson_paths = generate_geojson(all_segments)

    # generate map (passes merged_areas to JS so selector remembers older areas)
    mymap = generate_map(geojson_paths, centroids, merged_areas)

    # (optional) Google Analytics snippet - keep or remove as needed
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
    # inject GA just before </head>
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
