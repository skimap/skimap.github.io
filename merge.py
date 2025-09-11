import os
import folium
import gpxpy
import json
import math
from collections import defaultdict
import color as c
from tqdm import tqdm
from folium.plugins import LocateControl

# Usage of the index.html
# Running the index.html file as file:/// in the browser doesn't work
# Start a localhost in the directory of the project: "python -m http.server 8000"

# Configuration
#merge_directory = "tracks/raw/all"
merge_directory = "tracks/processed/all"
#coloring_scheme = 1
coloring_scheme = 3
output_geojson_dir = "tracks_geojson"
min_zoom_level = 14
line_width = 3
max_features_per_file = 2000
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
            return ([], 0)

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

        # Process segments in order
        segments = []
        skiing = 0

        for i in range(len(points) - 1):
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

            segments.append((color, [current_point, next_point]))

        return (segments, skiing)
    except Exception as e:
        print(f"Error processing {filename}: {str(e)}")
        return ([], 0)

def generate_geojson(all_segments):
    features = []
    for idx, (color, segment) in enumerate(all_segments):
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
                "min_zoom": min_zoom_level,
                "z_index": idx  # Preserve original order
            }
        })
    
    # Split features into chunks and compute chunk bounding boxes
    file_paths = []
    num_files = math.ceil(len(features) / max_features_per_file)
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
        with open(geojson_path, 'w') as f:
            json.dump({"type": "FeatureCollection", "features": chunk}, f)
        
        file_paths.append(geojson_path)
        chunk_bboxes[os.path.basename(geojson_path)] = bbox

    # Save chunk bounding boxes
    with open(os.path.join(output_geojson_dir, "chunk_bboxes.json"), 'w') as f:
        json.dump(chunk_bboxes, f)
    
    return file_paths

def generate_map(geojson_paths):
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
        
        // Layer group for all tracks
        const trackLayerGroup = L.layerGroup().addTo(map);
        
        // Load a single GeoJSON file
        async function loadGeoJSON(path) {{
            if (loadedFiles.has(path)) return;
            
            try {{
                const response = await fetch(path);
                const data = await response.json();
                
                const layer = L.geoJSON(data, {{
                    style: function(feature) {{
                        return {{
                            color: feature.properties.color,
                            weight: {line_width},
                            opacity: map.getZoom() >= MIN_ZOOM ? 1 : 0,
                            zIndex: feature.properties.z_index  // CORRECTED: Set zIndex in style
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
            
            map.on('movestart', function() {{
                trackLayerGroup.eachLayer(layer => {{
                    if (layer._renderer) {{
                        layer._renderer._container.style.display = 'none';
                    }}
                }});
            }});
            
            map.on('moveend', function() {{
                trackLayerGroup.eachLayer(layer => {{
                    if (layer._renderer) {{
                        layer._renderer._container.style.display = 'block';
                    }}
                }});
                throttledUpdateVisibility();
            }});
        }});
    }});
    </script>
    """
    
    mymap.get_root().html.add_child(folium.Element(script))
    return mymap

def main():
    all_segments = []  # Preserve segment order
    total_skiing = 0

    files = [f for f in os.listdir(merge_directory) if f.endswith(".gpx")]
    for filename in tqdm(files, desc="Processing tracks"):
        segments, skiing = process_gpx_file(filename)
        all_segments.extend(segments)
        total_skiing += skiing

    geojson_paths = generate_geojson(all_segments)
    mymap = generate_map(geojson_paths)
    
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
    print(f"Generated {len(geojson_paths)} GeoJSON files")
    print("Map generated: index.html")

if __name__ == "__main__":
    main()