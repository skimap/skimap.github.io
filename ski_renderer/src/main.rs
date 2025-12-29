use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{BufReader, Cursor, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;

use gpx::read;
use gpx::Gpx;
use rayon::prelude::*;
use tiny_skia::{Pixmap, Paint, PathBuilder, Stroke, Transform, LineCap, LineJoin};
use glob::glob;
use indicatif::{ProgressBar, ProgressStyle};
use chrono::{DateTime, Utc};
use serde_json::Value;

// --- CONFIGURATION ---
const TILE_SIZE: u32 = 512;
const MIN_ZOOM: u8 = 6;
const MAX_ZOOM: u8 = 19;

// UPDATE THESE PATHS IF NEEDED
const INPUT_DIR: &str = "../tracks/raw/all"; 
const OUTPUT_DIR: &str = "../tiles"; 
const LIFTS_FILE: &str = "../json/lifts/lifts.geojson";
const EARTH_RADIUS: f64 = 6371000.0;

// DEBUG
const DEBUG_MODE: bool = false; 
const DEBUG_DIR: &str = "d:/python/skimap.github.io/tiles/debug";

// COLORS (RGBA Hex)
const COL_LIFT_ACCESS: u32 = 0x80808060; 
const COL_UPHILL: u32      = 0x80808060; 

const COL_ULIGHT_GREEN: u32 = 0x48B74860; 
const COL_UDARK_GREEN: u32  = 0x00640060; 
const COL_ULIGHT_BLUE: u32  = 0x32A2D960; 
const COL_UBLUE: u32        = 0x0000FF60; 
const COL_UPURPLE: u32      = 0x80008060; 
const COL_UBRIGHT_RED: u32  = 0xff0a0060; 
const COL_UDARK_RED: u32    = 0x8b000060; 

const COL_LIGHT_GREEN: u32 = 0x48B748FF; 
const COL_DARK_GREEN: u32  = 0x006400FF; 
const COL_LIGHT_BLUE: u32  = 0x32A2D9FF; 
const COL_BLUE: u32        = 0x0000FFFF; 
const COL_PURPLE: u32      = 0x800080FF; 
const COL_BRIGHT_RED: u32  = 0xff0a00FF; 
const COL_DARK_RED: u32    = 0x8b0000FF; 
const COL_BLACK: u32       = 0x000000FF; 

// --- DATA STRUCTURES ---
#[derive(Clone, Debug)]
struct Point {
    lat: f64,
    lon: f64,
    ele: f64,
    time: Option<DateTime<Utc>>, 
}

#[derive(Clone)]
struct Segment {
    points: Vec<Point>,
    color: u32, 
}

// --- HIGH PERFORMANCE SPATIAL INDEX ---
struct LiftPath {
    points: Vec<(f64, f64)>, 
}

struct LiftDatabase {
    lifts: Vec<LiftPath>,
    grid: HashMap<(i32, i32), Vec<usize>>, 
    grid_size: f64, 
}

impl LiftDatabase {
    fn new() -> Self {
        LiftDatabase { 
            lifts: Vec::new(),
            grid: HashMap::new(),
            grid_size: 0.005, 
        }
    }

    fn add_interpolated_path(&mut self, points: Vec<(f64, f64)>) {
        if points.is_empty() { return; }
        let lift_idx = self.lifts.len();
        
        for &(lat, lon) in &points {
            let gx = (lat / self.grid_size).floor() as i32;
            let gy = (lon / self.grid_size).floor() as i32;
            for dx in -1..=1 {
                for dy in -1..=1 {
                    self.grid.entry((gx + dx, gy + dy)).or_default().push(lift_idx);
                }
            }
        }
        self.lifts.push(LiftPath { points });
    }

    // Returns: (Distance in meters, Vector of closest lift segment (dx, dy) in meters)
    fn get_nearest_lift_info(&self, lat: f64, lon: f64) -> (f64, Option<(f64, f64)>) {
        let gx = (lat / self.grid_size).floor() as i32;
        let gy = (lon / self.grid_size).floor() as i32;
        
        let mut min_dist = f64::MAX;
        let mut best_vector = None;

        if let Some(indices) = self.grid.get(&(gx, gy)) {
            for &idx in indices {
                let lift = &self.lifts[idx];
                for i in 0..lift.points.len()-1 {
                    let p1 = lift.points[i];
                    let p2 = lift.points[i+1];
                    let d = dist_to_segment(lat, lon, p1.0, p1.1, p2.0, p2.1);
                    
                    if d < min_dist {
                        min_dist = d;
                        
                        // Calculate the vector of this specific lift segment
                        // We project to local meters to match the user's vector calculation
                        let m_per_lat = 111111.0;
                        let m_per_lon = 111111.0 * to_rad(p1.0).cos();
                        
                        let dy = (p2.0 - p1.0) * m_per_lat;
                        let dx = (p2.1 - p1.1) * m_per_lon;
                        
                        best_vector = Some((dx, dy));

                        // Optimization: Close enough to stop searching?
                        if min_dist < 5.0 { return (min_dist, best_vector); }
                    }
                }
            }
        }
        (min_dist, best_vector)
    }
}

fn interpolate_points(raw_points: Vec<(f64, f64)>, step_meters: f64) -> Vec<(f64, f64)> {
    let mut result = Vec::new();
    if raw_points.is_empty() { return result; }
    result.push(raw_points[0]);
    for i in 0..raw_points.len()-1 {
        let (lat1, lon1) = raw_points[i];
        let (lat2, lon2) = raw_points[i+1];
        let dist = haversine_dist(lat1, lon1, lat2, lon2);
        if dist > step_meters {
            let num_steps = (dist / step_meters).ceil() as i32;
            for s in 1..num_steps {
                let fraction = s as f64 / num_steps as f64;
                result.push((lat1 + (lat2 - lat1) * fraction, lon1 + (lon2 - lon1) * fraction));
            }
        }
        result.push((lat2, lon2));
    }
    result
}

// --- MATH HELPERS ---
fn to_rad(deg: f64) -> f64 { deg * std::f64::consts::PI / 180.0 }
fn haversine_dist(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let dlat = to_rad(lat2 - lat1);
    let dlon = to_rad(lon2 - lon1);
    let a = (dlat / 2.0).sin().powi(2) + to_rad(lat1).cos() * to_rad(lat2).cos() * (dlon / 2.0).sin().powi(2);
    let c = 2.0 * a.sqrt().asin();
    EARTH_RADIUS * c
}
fn dist_to_segment(lat: f64, lon: f64, lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let meters_per_lat = 111111.0;
    let meters_per_lon = 111111.0 * to_rad(lat).cos();
    let x = lon * meters_per_lon; let y = lat * meters_per_lat;
    let x1 = lon1 * meters_per_lon; let y1 = lat1 * meters_per_lat;
    let x2 = lon2 * meters_per_lon; let y2 = lat2 * meters_per_lat;
    let dx = x2 - x1; let dy = y2 - y1;
    if dx == 0.0 && dy == 0.0 { return ((x - x1).powi(2) + (y - y1).powi(2)).sqrt(); }
    let t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy);
    let t_clamped = t.max(0.0).min(1.0);
    let closest_x = x1 + t_clamped * dx;
    let closest_y = y1 + t_clamped * dy;
    ((x - closest_x).powi(2) + (y - closest_y).powi(2)).sqrt()
}
fn latlon_to_tile(lat: f64, lon: f64, zoom: u8) -> (f64, f64) {
    let n = 2.0f64.powi(zoom as i32);
    let x = (lon + 180.0) / 360.0 * n;
    let lat_rad = to_rad(lat);
    let y = (1.0 - (lat_rad.tan().asinh()) / std::f64::consts::PI) / 2.0 * n;
    (x, y)
}
fn get_color_from_gradient(gradient: f64) -> u32 {
    if gradient >= -0.07 { return COL_LIGHT_GREEN; } 
    else if gradient >= -0.15 { return COL_DARK_GREEN; } 
    else if gradient >= -0.20 { return COL_LIGHT_BLUE; } 
    else if gradient >= -0.25 { return COL_BLUE; } 
    else if gradient >= -0.30 { return COL_PURPLE; } 
    else if gradient >= -0.37 { return COL_BRIGHT_RED; } 
    else if gradient >= -0.45 { return COL_DARK_RED; } 
    else { return COL_BLACK; }
}

fn get_color_from_ugradient(gradient: f64) -> u32 {
    if gradient <= 0.07 { return COL_ULIGHT_GREEN; } 
    else if gradient <= 0.15 { return COL_UDARK_GREEN; } 
    else if gradient <= 0.20 { return COL_ULIGHT_BLUE; } 
    else if gradient <= 0.25 { return COL_UBLUE; } 
    else if gradient <= 0.30 { return COL_UPURPLE; } 
    else if gradient <= 0.37 { return COL_UBRIGHT_RED; } 
    else if gradient <= 0.45 { return COL_UDARK_RED; } 
    else { return COL_BLACK; }
}

fn load_lifts() -> LiftDatabase {
    let mut db = LiftDatabase::new();
    let path = Path::new(LIFTS_FILE);
    if !path.exists() { 
        println!("WARNING: Lifts file not found at {:?}", path);
        return db; 
    }
    let file = File::open(path).expect("Failed to open lifts file");
    let reader = BufReader::new(file);
    let json: Value = serde_json::from_reader(reader).expect("Failed to parse GeoJSON");

    println!("Parsing Lift GeoJSON...");
    if let Some(features) = json["features"].as_array() {
        for feature in features {
            let geometry = &feature["geometry"];
            let type_str = geometry["type"].as_str().unwrap_or("");
            let coords_arrays = if type_str == "LineString" {
                 vec![geometry["coordinates"].clone()]
            } else if type_str == "MultiLineString" {
                 geometry["coordinates"].as_array().unwrap_or(&vec![]).clone()
            } else { vec![] };
            for line in coords_arrays {
                if let Some(pts) = line.as_array() {
                    let mut path_vec = Vec::new();
                    for pt in pts {
                        if let Some(pt_arr) = pt.as_array() {
                            if pt_arr.len() >= 2 {
                                let lon = pt_arr[0].as_f64().unwrap_or(0.0);
                                let lat = pt_arr[1].as_f64().unwrap_or(0.0);
                                path_vec.push((lat, lon));
                            }
                        }
                    }
                    if !path_vec.is_empty() { 
                        let dense_path = interpolate_points(path_vec, 5.0);
                        db.add_interpolated_path(dense_path); 
                    }
                }
            }
        }
    }
    for indices in db.grid.values_mut() { indices.sort_unstable(); indices.dedup(); }
    println!("Loaded & Interpolated {} lift segments.", db.lifts.len());
    db
}

fn process_gpx_file(path: PathBuf, lift_db: &LiftDatabase) -> Vec<Segment> {
    let content_res = fs::read_to_string(&path);
    if let Err(e) = content_res { println!("Error reading file {:?}: {}", path, e); return vec![]; }
    let mut content = content_res.unwrap();
    if content.contains("<metadate>") { content = content.replace("<metadate>", "<metadata>").replace("</metadate>", "</metadata>"); }
    let tags_to_remove = ["exerciseinfo"]; 
    for tag in tags_to_remove {
        let open_tag = format!("<{}", tag);
        let close_tag = format!("</{}>", tag);
        while let Some(start_idx) = content.find(&open_tag) {
            if let Some(end_offset) = content[start_idx..].find(&close_tag) {
                let end_idx = start_idx + end_offset + close_tag.len();
                content.replace_range(start_idx..end_idx, "");
            } else { break; }
        }
    }

    let reader = Cursor::new(content.as_bytes());
    let gpx_data: Gpx = match read(reader) {
        Ok(g) => g,
        Err(e) => { println!("GPX Parse Error for {:?}: {}", path, e); return vec![]; }
    };

    let mut debug_writer = if DEBUG_MODE {
        let _ = fs::create_dir_all(DEBUG_DIR);
        let file_name = path.file_stem().unwrap().to_string_lossy();
        let log_path = Path::new(DEBUG_DIR).join(format!("{}_debug.csv", file_name));
        let f = fs::File::create(log_path).ok();
        if let Some(mut file) = f {
            let _ = writeln!(file, "time,lat,lon,ele,gradient,sinuosity,avg_speed_mps,speed_cv,nearest_lift_m,parallelness,lift_score,final_color");
            Some(file)
        } else { None }
    } else { None };

    let mut file_segments = Vec::new();

    for track in gpx_data.tracks {
        for segment in track.segments {
            let raw_points: Vec<Point> = segment.points.iter().map(|p| Point {
                lat: p.point().y(), lon: p.point().x(), ele: p.elevation.unwrap_or(0.0),
                time: p.time.as_ref().and_then(|t| {
                    let s_clean = format!("{:?}", t).replace("Time(", "").replace(")", "").replace("\"", "");
                    if let Ok(dt) = DateTime::parse_from_rfc3339(&s_clean) { return Some(dt.with_timezone(&Utc)); }
                    let parts: Vec<&str> = s_clean.split_whitespace().collect();
                    if parts.len() >= 2 {
                        let date = parts[0];
                        let mut time = parts[1].to_string();
                        if let Some(idx) = time.find(':') { if idx == 1 { time = format!("0{}", time); } }
                        let iso = format!("{}T{}Z", date, time);
                        if let Ok(dt) = DateTime::parse_from_rfc3339(&iso) { return Some(dt.with_timezone(&Utc)); }
                    }
                    None
                }),
            }).collect();

            if raw_points.len() < 2 { continue; }

            let mut descent_rates = Vec::with_capacity(raw_points.len());
            descent_rates.push(0.0);
            for i in 0..raw_points.len()-1 {
                let dist = haversine_dist(raw_points[i].lat, raw_points[i].lon, raw_points[i+1].lat, raw_points[i+1].lon);
                let diff = raw_points[i+1].ele - raw_points[i].ele;
                descent_rates.push(if dist == 0.0 { 0.0 } else { diff / dist });
            }
            let mut gradient_avg = vec![0.0; descent_rates.len()];
            let window = 5;
            for i in 0..descent_rates.len() {
                let start = if i < window/2 { 0 } else { i - window/2 };
                let end = (i + window/2 + 1).min(descent_rates.len());
                let mut sum = 0.0; let mut count = 0.0;
                for j in start..end { sum += descent_rates[j]; count += 1.0; }
                gradient_avg[i] = if count > 0.0 { sum / count } else { 0.0 };
            }

            let mut current_seg_points = Vec::new();
            if !raw_points.is_empty() { current_seg_points.push(raw_points[0].clone()); }
            let mut current_color = COL_UPHILL; 
            let mut first_pass = true;
            let geo_window = 4;

            for i in 0..raw_points.len()-1 {
                let start = if i < geo_window { 0 } else { i - geo_window };
                let end = (i + geo_window + 1).min(raw_points.len());
                
                let mut path_dist = 0.0;
                for k in start..end-1 {
                    path_dist += haversine_dist(raw_points[k].lat, raw_points[k].lon, raw_points[k+1].lat, raw_points[k+1].lon);
                }
                let direct_dist = haversine_dist(raw_points[start].lat, raw_points[start].lon, raw_points[end-1].lat, raw_points[end-1].lon);
                let sinuosity = if direct_dist > 0.0 { path_dist / direct_dist } else { 1.0 };
                
                let mut speeds = Vec::new();
                for k in start..end-1 {
                    if let (Some(t1), Some(t2)) = (raw_points[k].time, raw_points[k+1].time) {
                         let d = haversine_dist(raw_points[k].lat, raw_points[k].lon, raw_points[k+1].lat, raw_points[k+1].lon);
                         let ms = t2.signed_duration_since(t1).num_milliseconds();
                         if ms > 100 { speeds.push(d / (ms as f64 / 1000.0)); }
                    }
                }
                let mut avg_speed = 0.0;
                let mut cv = 1.0; 
                if !speeds.is_empty() {
                    avg_speed = speeds.iter().sum::<f64>() / speeds.len() as f64;
                    if avg_speed > 0.1 {
                        let variance = speeds.iter().map(|s| (s - avg_speed).powi(2)).sum::<f64>() / speeds.len() as f64;
                        cv = variance.sqrt() / avg_speed;
                    }
                }

                let grad = gradient_avg[i];
                let (nearest_lift_dist, nearest_lift_vec) = lift_db.get_nearest_lift_info(raw_points[i].lat, raw_points[i].lon);
                
                // --- PARALLELISM CHECK ---
                let mut parallel_factor = 0.0;
                
                if let Some((lx, ly)) = nearest_lift_vec {
                    // Calculate User Vector for this segment
                    let m_per_lat = 111111.0;
                    let m_per_lon = 111111.0 * to_rad(raw_points[i].lat).cos();
                    let uy = (raw_points[i+1].lat - raw_points[i].lat) * m_per_lat;
                    let ux = (raw_points[i+1].lon - raw_points[i].lon) * m_per_lon;
                    
                    let mag_u = (ux*ux + uy*uy).sqrt();
                    let mag_l = (lx*lx + ly*ly).sqrt();
                    
                    if mag_u > 0.1 && mag_l > 0.1 {
                        // Dot Product of normalized vectors
                        // Result: 1.0 (Parallel), 0.0 (Perpendicular), -1.0 (Opposite)
                        // We use ABS() because Lift GeoJSON direction might be arbitrary
                        let dot = (ux*lx + uy*ly) / (mag_u * mag_l);
                        parallel_factor = dot.abs();
                    }
                }

                // --- WEIGHTED SCORING SYSTEM ---
                let mut lift_score = 0.0;

                // 1. Proximity Score (Max 60)
                if nearest_lift_dist < 2.5 {
                    lift_score += 55.0;
                } else if nearest_lift_dist < 10.0 {
                    lift_score += 55.0 * (1.0 - (nearest_lift_dist - 2.5) / 7.5);
                }

                // 2. Parallelism Score (Max 30)
                // If aligned (> 0.9), big bonus. If perpendicular (< 0.5), penalty.
                if parallel_factor > 0.95 {
                    lift_score += 30.0; // PERFECT ALIGNMENT
                } else if parallel_factor > 0.85 {
                    lift_score += 15.0; // OK ALIGNMENT
                } else if parallel_factor < 0.5 {
                    lift_score -= 20.0; // CROSSING UNDER LIFT
                }

                // 3. Stability Score (Max 20)
                if cv < 0.30 { lift_score += 15.0; }
                else if cv < 0.50 { lift_score += 5.0; }

                if sinuosity < 1.10 { lift_score += 10.0; }
                else if sinuosity < 1.25 { lift_score += 5.0; }

                // 4. Gradient Penalty / Bonus
                if grad >= 0.0 {
                     lift_score += (grad * 100.0).min(20.0);
                } else {
                     // Steep Downhill penalty
                     lift_score += grad * 200.0;
                }

                // Final Decision
                let is_lift = lift_score >= 55.0;

                let next_color;
                if is_lift {
                    next_color = COL_LIFT_ACCESS;
                } else if grad >= 0.0 {
                    next_color = get_color_from_ugradient(grad); 
                } else {
                    next_color = get_color_from_gradient(grad);
                }

                if let Some(w) = &mut debug_writer {
                    let time_str = raw_points[i].time.map(|t| t.to_rfc3339()).unwrap_or("".to_string());
                    let _ = writeln!(w, "{},{},{},{},{:.4},{:.4},{:.2},{:.4},{:.2},{:.2},{:.2},{:X}",
                        time_str, raw_points[i].lat, raw_points[i].lon, raw_points[i].ele,
                        grad, sinuosity, avg_speed, cv, nearest_lift_dist, parallel_factor, lift_score, next_color
                    );
                }

                if first_pass { current_color = next_color; first_pass = false; }
                current_seg_points.push(raw_points[i+1].clone());

                if next_color != current_color {
                    if current_seg_points.len() >= 2 {
                        file_segments.push(Segment { points: current_seg_points.clone(), color: current_color });
                    }
                    current_seg_points.clear();
                    current_seg_points.push(raw_points[i].clone()); 
                    current_seg_points.push(raw_points[i+1].clone());
                    current_color = next_color;
                }
            }
            if current_seg_points.len() >= 2 {
                file_segments.push(Segment { points: current_seg_points, color: current_color });
            }
        }
    }
    file_segments
}

fn generate_tile(zoom: u8, tile_x: u32, tile_y: u32, segments: &[&Segment]) {
    let dir_path = format!("{}/{}/{}", OUTPUT_DIR, zoom, tile_x);
    let file_path = format!("{}/{}.png", dir_path, tile_y);
    let mut pixmap = Pixmap::new(TILE_SIZE, TILE_SIZE).unwrap();
    let base_width_algo = ((zoom as f32 - 10.0) / 2.0).floor() + 5.0;
    let final_width = base_width_algo.max(4.0).min(10.0);
    let line_width = final_width * 0.8; 
    let mut paint = Paint::default(); paint.anti_alias = true;
    let stroke = Stroke { width: line_width, line_cap: LineCap::Round, line_join: LineJoin::Round, ..Stroke::default() };
    for seg in segments {
        if seg.points.len() < 2 { continue; }
        let mut pb = PathBuilder::new();
        let mut first = true;
        let mut points_buf = Vec::with_capacity(seg.points.len());
        for p in &seg.points {
            let (tx, ty) = latlon_to_tile(p.lat, p.lon, zoom);
            let px = ((tx - tile_x as f64) * TILE_SIZE as f64) as f32;
            let py = ((ty - tile_y as f64) * TILE_SIZE as f64) as f32;
            points_buf.push((px, py));
        }
        for (px, py) in points_buf {
            if first { pb.move_to(px, py); first = false; } else { pb.line_to(px, py); }
        }
        if let Some(path) = pb.finish() {
            let color = seg.color;
            let r = ((color >> 24) & 0xFF) as u8; let g = ((color >> 16) & 0xFF) as u8;
            let b = ((color >> 8) & 0xFF) as u8; let a = (color & 0xFF) as u8; 
            paint.set_color_rgba8(r, g, b, a);
            pixmap.stroke_path(&path, &paint, &stroke, Transform::identity(), None);
        }
    }
    if pixmap.data().chunks(4).any(|p| p[3] > 10) {
        fs::create_dir_all(&dir_path).unwrap_or_default();
        pixmap.save_png(&file_path).unwrap();
    }
}

fn main() {
    let start_time = Instant::now();
    println!("Starting Rust Ski Renderer (v15 - Parallelism Check)...");
    
    println!("Loading Lifts...");
    let lift_db = Arc::new(load_lifts());

    let pattern = format!("{}/*.gpx", INPUT_DIR);
    let paths: Vec<PathBuf> = glob(&pattern).expect("Failed to read glob pattern").filter_map(Result::ok).collect();
    println!("Found {} GPX files.", paths.len());

    let all_segments: Vec<Segment> = paths.par_iter()
        .flat_map(|p| process_gpx_file(p.clone(), &lift_db))
        .collect();
    
    println!("Processed {} segments in {:.2?}s", all_segments.len(), start_time.elapsed());
    
    for zoom in MIN_ZOOM..=MAX_ZOOM {
        println!("Zoom Level {}...", zoom);
        let tile_buckets: HashMap<(u32, u32), Vec<usize>> = all_segments.iter().enumerate().fold(
            HashMap::new(), 
            |mut acc, (idx, seg)| {
                let mut min_x = f64::MAX; let mut max_x = f64::MIN;
                let mut min_y = f64::MAX; let mut max_y = f64::MIN;
                for p in &seg.points {
                    let (tx, ty) = latlon_to_tile(p.lat, p.lon, zoom);
                    min_x = min_x.min(tx); max_x = max_x.max(tx);
                    min_y = min_y.min(ty); max_y = max_y.max(ty);
                }
                let start_x = (min_x - 0.5).floor() as i64;
                let end_x = (max_x + 0.5).floor() as i64;
                let start_y = (min_y - 0.5).floor() as i64;
                let end_y = (max_y + 0.5).floor() as i64;
                for tx in start_x..=end_x {
                    for ty in start_y..=end_y {
                        if tx >= 0 && ty >= 0 { acc.entry((tx as u32, ty as u32)).or_default().push(idx); }
                    }
                }
                acc
            }
        );

        let tiles: Vec<((u32, u32), Vec<usize>)> = tile_buckets.into_iter().collect();
        let pb = ProgressBar::new(tiles.len() as u64);
        pb.set_style(ProgressStyle::default_bar().template("[{elapsed_precise}] {bar:40.cyan/blue} {pos}/{len} ({eta})").unwrap());
        tiles.par_iter().for_each(|((tx, ty), seg_indices)| {
            let seg_refs: Vec<&Segment> = seg_indices.iter().map(|&i| &all_segments[i]).collect();
            generate_tile(zoom, *tx, *ty, &seg_refs);
            pb.inc(1);
        });
        pb.finish();
    }
    println!("Done. Total time: {:.2?}s", start_time.elapsed());
}