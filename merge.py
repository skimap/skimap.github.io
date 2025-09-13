import os
import shutil
import folium
import gpxpy
import json
import math
from collections import defaultdict
import color as c
from tqdm import tqdm
from folium.plugins import LocateControl
import shapely.geometry as geom
from geopy.distance import distance as geo_distance

# Usage of the index.html
# Running the index.html file as file:/// in the browser doesn't work
# Start a localhost in the directory of the project: "python -m http.server 8000"

# Configuration
merge_directory = "tracks/processed/all"
coloring_scheme = 4
output_geojson_dir = "tracks_geojson"
min_zoom_level = 14
line_width = 3
max_features_per_file = 2000

# Create (or reuse) the directory
os.makedirs(output_geojson_dir, exist_ok=True)

# Clear all files inside the directory
for filename in os.listdir(output_geojson_dir):
    file_path = os.path.join(output_geojson_dir, filename)
    if os.path.isfile(file_path) or os.path.islink(file_path):
        os.unlink(file_path)   # remove file or symlink
    elif os.path.isdir(file_path):
        shutil.rmtree(file_path)  # remove subdirectory

# Load lift data
with open('json/lifts/lifts_e.json', encoding='utf-8') as f:
    lifts_e = json.load(f)
# lifts_e expected shape: [[lat, lon], ...] or similar; original code used (lift[1], lift[0])
# keep the same ordering as you used before:
lift_end_coordinate_tuples = [(lift[1], lift[0]) for lift in lifts_e]

# Load ski area polygons
with open("json/ski_areas/ski_areas.geojson", encoding="utf-8") as f:
    ski_areas_data = json.load(f)

# (Optional) build a convenience list of (name, shapely_geometry)
ski_areas = []
for feature in ski_areas_data.get("features", []):
    name = feature.get("properties", {}).get("name", "Unknown")
    shape_obj = geom.shape(feature["geometry"])
    ski_areas.append((name, shape_obj))


def assign_ski_area(points, max_km=2):
    """
    Assign ski area name based on centroid of the track.
    Returns a string ski area name (or "Unknown").
    """
    if not points:
        return "Unknown"

    # Build LineString from track points (lon, lat) order for shapely
    line = geom.LineString([(lon, lat) for lat, lon, _ in points])
    centroid = line.centroid  # shapely Point

    # Iterate features from loaded geojson
    for feature in ski_areas_data.get("features", []):
        name = feature.get("properties", {}).get("name", "Unknown")
        geometry = geom.shape(feature["geometry"])

        # If centroid is inside geometry → match
        try:
            if geometry.contains(centroid):
                return name
        except Exception:
            # Some geometries may be invalid; continue gracefully
            pass

        # Only for Polygon or MultiPolygon → check distance to exterior coordinates
        if isinstance(geometry, (geom.Polygon, geom.MultiPolygon)):
            polygons = [geometry] if isinstance(geometry, geom.Polygon) else list(geometry.geoms)
            # For each polygon, compute min geodesic distance between centroid and polygon exterior coordinates
            try:
                poly_min_dists = []
                for poly in polygons:
                    # poly.exterior.coords yields sequence of (lon, lat) pairs (shapely uses x=lon, y=lat)
                    coords = list(poly.exterior.coords)
                    if not coords:
                        continue
                    # compute min distance (in km) from centroid to any vertex on exterior
                    c_latlon = (centroid.y, centroid.x)
                    vertex_min = min(
                        geo_distance(c_latlon, (coord[1], coord[0])).km
                        for coord in coords
                    )
                    poly_min_dists.append(vertex_min)

                if poly_min_dists and min(poly_min_dists) <= max_km:
                    return name
            except Exception:
                # if something unexpected happens (e.g., invalid geometry), skip this feature
                pass

        # Point geometry: direct distance check
        elif isinstance(geometry, geom.Point):
            try:
                if geo_distance((centroid.y, centroid.x), (geometry.y, geometry.x)).km <= max_km:
                    return name
            except Exception:
                pass

        # Optionally: LineString geometry could be tested similarly (skipped here)

    # Fallback: no match
    return "Unknown"


def process_gpx_file(filename):
    try:
        file_path = os.path.join(merge_directory, filename)
        with open(file_path, 'r', encoding='utf-8') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        points = []
        for track in gpx.tracks:
            for segment in track.segments:
                # ensure p.elevation may be None — keep as None or 0 if you prefer
                points.extend([(p.latitude, p.longitude, p.elevation if p.elevation is not None else 0) for p in segment.points])

        if len(points) < 2:
            return ([], 0, None)

        # Assign ski area once per track (string)
        ski_area_name = assign_ski_area(points)

        # --- compute centroid ---
        line = geom.LineString([(lon, lat) for lat, lon, _ in points])
        centroid = line.centroid
        centroid_coords = (centroid.y, centroid.x)

        # Calculate descent rates and moving average
        descent_rates = []
        for i in range(1, len(points)):
            h_dist = gpxpy.geo.haversine_distance(
                points[i-1][0], points[i-1][1],
                points[i][0], points[i][1]
            )
            elevation_gain = points[i][2] - points[i-1][2]
            descent_rates.append(elevation_gain / h_dist if h_dist != 0 else 0)

        # moving_avg length = len(descent_rates)
        # use window of 5 (as in original), but careful with short lists
        window = 5
        moving_avg = []
        for i in range(len(descent_rates)):
            start = max(0, i - (window - 1))
            window_vals = descent_rates[start:i+1]
            # avoid division by zero if window_vals empty (shouldn't be)
            moving_avg.append(sum(window_vals) / window)

        # Process segments in order
        segments = []
        skiing = 0

        for i in range(len(points) - 1):
            if i >= len(moving_avg):
                break

            current_point = (points[i][0], points[i][1])
            next_point = (points[i+1][0], points[i+1][1])

            # Determine color for this segment
            if i >= 5 and all(m >= 0 for m in moving_avg[max(0, i-5):i]) and moving_avg[i] < 0:
                # check proximity to lifts
                if any(gpxpy.geo.haversine_distance(*current_point, *lift) < 50 for lift in lift_end_coordinate_tuples):
                    color = "#4a412a"
                    skiing += 1
                else:
                    color = c.get_color(moving_avg[i], coloring_scheme)
            else:
                color = c.get_color(moving_avg[i], coloring_scheme)

            # segments: (color, [start, end], ski_area_name)
            segments.append((color, [current_point, next_point], ski_area_name))

        return (segments, skiing, centroid_coords)
    except Exception as e:
        print(f"Error processing {filename}: {str(e)}")
        return ([], 0, None)


def generate_geojson(all_segments):
    features = []
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

    # Split features into chunks and compute chunk bounding boxes
    file_paths = []
    num_files = math.ceil(len(features) / max_features_per_file) if features else 0
    chunk_bboxes = {}

    for i in range(num_files):
        start_idx = i * max_features_per_file
        end_idx = min((i + 1) * max_features_per_file, len(features))
        chunk = features[start_idx:end_idx]

        # Calculate bounding box for the chunk
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

        geojson_path = os.path.join(output_geojson_dir, f"tracks_{i}.geojson")
        with open(geojson_path, 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": chunk}, f, ensure_ascii=False)

        file_paths.append(geojson_path)
        chunk_bboxes[os.path.basename(geojson_path)] = bbox

    # Save chunk bounding boxes
    with open(os.path.join(output_geojson_dir, "chunk_bboxes.json"), 'w', encoding='utf-8') as f:
        json.dump(chunk_bboxes, f, ensure_ascii=False)

    return file_paths


def generate_map(geojson_paths, centroids):
    # Create map with optimized settings
    mymap = folium.Map(
        location=[47.85, 16.01],
        zoom_start=6,
        max_zoom=19,
        prefer_canvas=True,
        tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attr='Map data © OpenStreetMap contributors'
    )

    # Add locate control
    LocateControl(
        auto_start=False,
        strings={"title": "Show my location"},
        position="topright",
        locate_options={"enableHighAccuracy": True}
    ).add_to(mymap)

    # Add ski area selector UI
    selector_html = """
    <div id="ski-selector" style="position:absolute;top:10px;right:50px;z-index:1000;background:white;padding:5px;border-radius:8px;">
        <label for="area">Ski Area:</label>
        <select id="area">
            <option value="all">All</option>
        </select>
    </div>
    """
    mymap.get_root().html.add_child(folium.Element(selector_html))

    # Pass ski area polygons to JS
    with open("json/ski_areas/ski_areas.geojson", encoding="utf-8") as f:
        ski_area_json = json.load(f)

    ski_area_js = json.dumps({
        f["properties"].get("name", "Unknown"): f["geometry"]
        for f in ski_area_json["features"]
    })

    # Asynchronous loading with spatial indexing
    script = f"""
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        const map = window['{mymap.get_name()}'];
        const MIN_ZOOM = {min_zoom_level};
        let loadedFiles = new Set();
        let lastUpdate = 0;
        const UPDATE_INTERVAL = 100;
        const MAX_LOAD_DISTANCE = 0.2;
        const skiAreas = {ski_area_js};

        // Layer group for all tracks
        const trackLayerGroup = L.layerGroup().addTo(map);
        let availableAreas = new Set();
        
        // Load a single GeoJSON file
        async function loadGeoJSON(path) {{
            if (loadedFiles.has(path)) return;
            
            try {{
                const response = await fetch(path);
                const data = await response.json();

                data.features.forEach(f => availableAreas.add(f.properties.ski_area));
                
                const layer = L.geoJSON(data, {{
                    filter: function(feature) {{
                        const selectedArea = document.getElementById("area").value;
                        return selectedArea === "all" || feature.properties.ski_area === selectedArea;
                    }},
                    style: function(feature) {{
                        return {{
                            color: feature.properties.color,
                            weight: {line_width},
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
                updateSelector();
                console.log(`Loaded: ${{path}}`);
            }} catch (error) {{
                console.error('Failed to load track file:', path, error);
            }}
        }}
        
        function updateSelector() {{
            const selector = document.getElementById("area");
            const existing = new Set(Array.from(selector.options).map(o => o.value));
            availableAreas.forEach(area => {{
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

            // Zoom to ski area polygon
            if (selectedArea !== "all" && skiAreas[selectedArea]) {{
                const layer = L.geoJSON(skiAreas[selectedArea]);
                map.fitBounds(layer.getBounds(), {{ maxZoom: MIN_ZOOM }});
                if (map.getZoom() < MIN_ZOOM) {{
                    map.setZoom(MIN_ZOOM);
                }}
            }}
        }});
        
        // Get features in current view
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
        
        // Load visible features
        async function loadVisibleFeatures() {{
            if (map.getZoom() < MIN_ZOOM) return;
            const filesToLoad = await getFeaturesInView();
            const loadPromises = filesToLoad.map(path => 
                loadGeoJSON(`tracks_geojson/${{path}}`)
            );
            await Promise.all(loadPromises);
        }}
        
        // Throttled visibility update
        function throttledUpdateVisibility() {{
            const now = Date.now();
            if (now - lastUpdate > UPDATE_INTERVAL) {{
                updateVisibility();
                lastUpdate = now;
            }}
        }}
        
        // Update track visibility
        function updateVisibility() {{
            const currentZoom = map.getZoom();
            const shouldShow = currentZoom >= MIN_ZOOM;
            
            trackLayerGroup.eachLayer(layer => {{
                layer.eachLayer(featureLayer => {{
                    featureLayer.setStyle({{ opacity: shouldShow ? 1 : 0 }});
                }});
            }});
            
            if (shouldShow) {{
                loadVisibleFeatures();
            }}
        }}
        
        // Initialize
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


def main():
    all_segments = []  # Preserve segment order
    total_skiing = 0
    centroids = []

    files = [f for f in os.listdir(merge_directory) if f.endswith(".gpx")]
    for filename in tqdm(files, desc="Processing tracks"):
        segments, skiing, centroid = process_gpx_file(filename)
        all_segments.extend(segments)
        total_skiing += skiing
        if centroid:
            # get ski_area name again for centroid listing (if desired)
            # but better to use the ski_area attached to segments if you want accurate association
            # here we compute assignment once more from centroid points (or skip)
            # simplest: derive from segments if available
            centroids.append({"coords": centroid})

    geojson_paths = generate_geojson(all_segments)
    mymap = generate_map(geojson_paths, centroids)

    # Add Google Analytics
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
    html_content = html_content.replace("</head>", google_analytics + "</head>", 1)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nTotal skiing segments detected: {total_skiing}")
    print(f"Generated {len(geojson_paths)} GeoJSON files")
    print("Map generated: index.html")


if __name__ == "__main__":
    main()
