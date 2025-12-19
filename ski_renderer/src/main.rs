use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{BufReader, Cursor};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;

use gpx::read;
use gpx::Gpx;
use rayon::prelude::*;
use tiny_skia::{Pixmap, Paint, PathBuilder, Stroke, Transform, LineCap, LineJoin};
use glob::glob;
use indicatif::{ProgressBar, ProgressStyle};
use serde::Deserialize;

// --- CONFIGURATION ---
const TILE_SIZE: u32 = 512;
const MIN_ZOOM: u8 = 10;
const MAX_ZOOM: u8 = 19;

// UPDATE THESE PATHS IF NEEDED
const INPUT_DIR: &str = "d:/python/skimap.github.io/tracks/raw/all"; 
const OUTPUT_DIR: &str = "d:/python/skimap.github.io/tiles"; 
const LIFTS_FILE: &str = "d:/python/skimap.github.io/json/lifts/lifts_e.json";
const EARTH_RADIUS: f64 = 6371000.0;

// --- COLORS (RGBA Hex) ---
const COL_LIFT_ACCESS: u32 = 0x4a412aFF; 

// Scheme 2 Palette
const COL_UPHILL: u32      = 0x80808080; 
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
}

#[derive(Clone)]
struct Segment {
    points: Vec<Point>,
    color: u32, 
}

type LiftData = Vec<serde_json::Value>; 

struct LiftIndex {
    coords: Vec<(f64, f64)>,
}

// --- MATH HELPERS ---
fn to_rad(deg: f64) -> f64 {
    deg * std::f64::consts::PI / 180.0
}

fn haversine_dist(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let dlat = to_rad(lat2 - lat1);
    let dlon = to_rad(lon2 - lon1);
    let a = (dlat / 2.0).sin().powi(2)
        + to_rad(lat1).cos() * to_rad(lat2).cos() * (dlon / 2.0).sin().powi(2);
    let c = 2.0 * a.sqrt().asin();
    EARTH_RADIUS * c
}

fn latlon_to_tile(lat: f64, lon: f64, zoom: u8) -> (f64, f64) {
    let n = 2.0f64.powi(zoom as i32);
    let x = (lon + 180.0) / 360.0 * n;
    let lat_rad = to_rad(lat);
    let y = (1.0 - (lat_rad.tan().asinh()) / std::f64::consts::PI) / 2.0 * n;
    (x, y)
}

// --- COLOR LOGIC ---
fn get_color_from_gradient(gradient: f64) -> u32 {
    if gradient >= 0.0 {
        return COL_UPHILL;      
    } else if gradient >= -0.07 {
        return COL_LIGHT_GREEN; 
    } else if gradient >= -0.15 {
        return COL_DARK_GREEN;  
    } else if gradient >= -0.20 {
        return COL_LIGHT_BLUE;  
    } else if gradient >= -0.25 {
        return COL_BLUE;        
    } else if gradient >= -0.30 {
        return COL_PURPLE;      
    } else if gradient >= -0.37 {
        return COL_BRIGHT_RED;  
    } else if gradient >= -0.45 {
        return COL_DARK_RED;    
    } else {
        return COL_BLACK;       
    }
}

// --- LIFT PROCESSING ---
fn load_lifts() -> LiftIndex {
    let path = Path::new(LIFTS_FILE);
    if !path.exists() {
        return LiftIndex { coords: vec![] };
    }
    let file = File::open(path).expect("Failed to open lifts file");
    let reader = BufReader::new(file);
    let json_data: LiftData = serde_json::from_reader(reader).expect("Failed to parse lifts JSON");

    let mut coords = Vec::new();
    for item in json_data {
        if let Some(arr) = item.as_array() {
            if arr.len() >= 3 {
                if let (Some(lat), Some(lon)) = (arr[1].as_f64(), arr[2].as_f64()) {
                    coords.push((lat, lon));
                }
            }
        }
    }
    LiftIndex { coords }
}

impl LiftIndex {
    fn is_near_lift(&self, lat: f64, lon: f64) -> bool {
        for &(l_lat, l_lon) in &self.coords {
            if (lat - l_lat).abs() > 0.001 || (lon - l_lon).abs() > 0.001 { continue; }
            if haversine_dist(lat, lon, l_lat, l_lon) < 50.0 {
                return true;
            }
        }
        false
    }
}

// --- GPX PROCESSING ---
fn process_gpx_file(path: PathBuf, lift_index: &LiftIndex) -> Vec<Segment> {
    // 1. Read file as string
    let content_res = fs::read_to_string(&path);
    if let Err(e) = content_res {
        println!("Error reading file {:?}: {}", path, e);
        return vec![];
    }
    
    let mut content = content_res.unwrap();
    
    // 2. SANITIZATION STEP
    // Fix Samsung Health Typos
    if content.contains("<metadate>") {
        content = content.replace("<metadate>", "<metadata>").replace("</metadate>", "</metadata>");
    }

    // Remove invalid non-standard tags like <exerciseinfo>...</exerciseinfo>
    // We do this by finding the start/end and removing the range
    let tags_to_remove = ["exerciseinfo"]; 
    
    for tag in tags_to_remove {
        let open_tag = format!("<{}", tag);
        let close_tag = format!("</{}>", tag);
        
        while let Some(start_idx) = content.find(&open_tag) {
            if let Some(end_offset) = content[start_idx..].find(&close_tag) {
                let end_idx = start_idx + end_offset + close_tag.len();
                content.replace_range(start_idx..end_idx, "");
            } else {
                // Malformed tag or self-closing without close tag. 
                // Break to avoid infinite loop.
                break;
            }
        }
    }

    // 3. Parse sanitized content
    let reader = Cursor::new(content.as_bytes());
    
    let gpx_data: Gpx = match read(reader) {
        Ok(g) => g,
        Err(e) => {
            println!("GPX Parse Error for {:?}: {}", path, e);
            return vec![];
        }
    };

    let mut file_segments = Vec::new();

    for track in gpx_data.tracks {
        for segment in track.segments {
            let raw_points: Vec<Point> = segment.points.iter().map(|p| Point {
                lat: p.point().y(),
                lon: p.point().x(),
                ele: p.elevation.unwrap_or(0.0),
            }).collect();

            if raw_points.len() < 2 { continue; }

            let mut descent_rates = Vec::with_capacity(raw_points.len());
            descent_rates.push(0.0);

            for i in 0..raw_points.len()-1 {
                let dist = haversine_dist(raw_points[i].lat, raw_points[i].lon, 
                                          raw_points[i+1].lat, raw_points[i+1].lon);
                let ele_diff = raw_points[i+1].ele - raw_points[i].ele;
                let rate = if dist == 0.0 { 0.0 } else { ele_diff / dist };
                descent_rates.push(rate);
            }

            let mut moving_avg = vec![0.0; descent_rates.len()];
            let window = 5;
            for i in 0..descent_rates.len() {
                let start = if i < window/2 { 0 } else { i - window/2 };
                let end = (i + window/2 + 1).min(descent_rates.len());
                let mut sum = 0.0;
                let mut count = 0.0;
                for j in start..end {
                    sum += descent_rates[j];
                    count += 1.0;
                }
                moving_avg[i] = if count > 0.0 { sum / count } else { 0.0 };
            }

            let mut current_seg_points = Vec::new();
            if !raw_points.is_empty() {
                current_seg_points.push(raw_points[0].clone());
            }
            
            let mut current_color = COL_UPHILL; 
            let mut first_pass = true;

            for i in 0..raw_points.len()-1 {
                let ma_curr = moving_avg[i];
                let mut is_transition = false;

                if i >= 5 {
                    let mut all_prev_non_neg = true;
                    for k in 1..=5 {
                         if moving_avg[i-k] < 0.0 { all_prev_non_neg = false; break; }
                    }
                    if all_prev_non_neg && ma_curr < 0.0 {
                        is_transition = true;
                    }
                }

                let next_color;
                if is_transition && lift_index.is_near_lift(raw_points[i].lat, raw_points[i].lon) {
                    next_color = COL_LIFT_ACCESS;
                } else {
                    next_color = get_color_from_gradient(ma_curr);
                }

                if first_pass {
                    current_color = next_color;
                    first_pass = false;
                }

                current_seg_points.push(raw_points[i+1].clone());

                if next_color != current_color {
                    if current_seg_points.len() >= 2 {
                        file_segments.push(Segment {
                            points: current_seg_points.clone(),
                            color: current_color,
                        });
                    }
                    current_seg_points.clear();
                    current_seg_points.push(raw_points[i+1].clone());
                    current_color = next_color;
                }
            }

            if current_seg_points.len() >= 2 {
                file_segments.push(Segment {
                    points: current_seg_points,
                    color: current_color,
                });
            }
        }
    }
    file_segments
}

// --- TILE GENERATION ---
fn generate_tile(zoom: u8, tile_x: u32, tile_y: u32, segments: &[&Segment]) {
    let dir_path = format!("{}/{}/{}", OUTPUT_DIR, zoom, tile_x);
    let file_path = format!("{}/{}.png", dir_path, tile_y);
    
    // NOTE: We do NOT skip if file exists. We overwrite to fix bad tiles.

    let mut pixmap = Pixmap::new(TILE_SIZE, TILE_SIZE).unwrap();
    
    let base_width_algo = ((zoom as f32 - 10.0) / 2.0).floor() + 5.0;
    let final_width = base_width_algo.max(4.0).min(10.0);
    let line_width = final_width * 0.8; 
    let margin = line_width / 2.0 + 2.0; 

    let mut paint = Paint::default();
    paint.anti_alias = true;
    
    let stroke = Stroke {
        width: line_width,
        line_cap: LineCap::Round,
        line_join: LineJoin::Round,
        ..Stroke::default()
    };
    
    for seg in segments {
        if seg.points.len() < 2 { continue; }

        let mut pb = PathBuilder::new();
        let mut first = true;
        
        let mut s_min_x = f32::MAX;
        let mut s_max_x = f32::MIN;
        let mut s_min_y = f32::MAX;
        let mut s_max_y = f32::MIN;

        let mut points_buf = Vec::with_capacity(seg.points.len());

        for p in &seg.points {
            let (tx, ty) = latlon_to_tile(p.lat, p.lon, zoom);
            let px = ((tx - tile_x as f64) * TILE_SIZE as f64) as f32;
            let py = ((ty - tile_y as f64) * TILE_SIZE as f64) as f32;
            
            s_min_x = s_min_x.min(px);
            s_max_x = s_max_x.max(px);
            s_min_y = s_min_y.min(py);
            s_max_y = s_max_y.max(py);

            points_buf.push((px, py));
        }

        if s_max_x < -margin || s_min_x > (TILE_SIZE as f32 + margin) ||
           s_max_y < -margin || s_min_y > (TILE_SIZE as f32 + margin) {
            continue;
        }

        for (px, py) in points_buf {
            if first {
                pb.move_to(px, py);
                first = false;
            } else {
                pb.line_to(px, py);
            }
        }

        if let Some(path) = pb.finish() {
            let color = seg.color;
            let r = ((color >> 24) & 0xFF) as u8;
            let g = ((color >> 16) & 0xFF) as u8;
            let b = ((color >> 8) & 0xFF) as u8;
            let a = (color & 0xFF) as u8; 
            
            paint.set_color_rgba8(r, g, b, a);
            pixmap.stroke_path(&path, &paint, &stroke, Transform::identity(), None);
        }
    }

    // STRICT PIXEL CHECK
    let data = pixmap.data();
    let has_content = data.chunks(4).any(|pixel| pixel[3] > 10);

    if has_content {
        fs::create_dir_all(&dir_path).unwrap_or_default();
        pixmap.save_png(&file_path).unwrap();
    }
}

fn main() {
    let start_time = Instant::now();
    println!("Starting Rust Ski Renderer (Sanitization Mode)...");

    println!("Loading Lift Data...");
    let lift_index = Arc::new(load_lifts());

    let pattern = format!("{}/*.gpx", INPUT_DIR);
    let paths: Vec<PathBuf> = glob(&pattern).expect("Failed to read glob pattern").filter_map(Result::ok).collect();
    println!("Found {} GPX files.", paths.len());

    println!("Parsing GPX files & calculating colors...");
    let all_segments: Vec<Segment> = paths.par_iter()
        .flat_map(|p| process_gpx_file(p.clone(), &lift_index))
        .collect();
    
    println!("Processed {} segments in {:.2?}s", all_segments.len(), start_time.elapsed());

    println!("Generating Tiles...");
    
    for zoom in MIN_ZOOM..=MAX_ZOOM {
        println!("Processing Zoom Level {}...", zoom);
        
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
                
                let padding = 0.5;
                let start_x = (min_x - padding).floor() as i64;
                let end_x = (max_x + padding).floor() as i64;
                let start_y = (min_y - padding).floor() as i64;
                let end_y = (max_y + padding).floor() as i64;

                for tx in start_x..=end_x {
                    for ty in start_y..=end_y {
                        if tx >= 0 && ty >= 0 {
                            acc.entry((tx as u32, ty as u32)).or_default().push(idx);
                        }
                    }
                }
                acc
            }
        );

        println!("  Zoom {}: {} potential tiles.", zoom, tile_buckets.len());

        let tiles: Vec<((u32, u32), Vec<usize>)> = tile_buckets.into_iter().collect();
        
        let pb = ProgressBar::new(tiles.len() as u64);
        pb.set_style(ProgressStyle::default_bar()
            .template("[{elapsed_precise}] {bar:40.cyan/blue} {pos}/{len} ({eta})")
            .unwrap());

        tiles.par_iter().for_each(|((tx, ty), seg_indices)| {
            let seg_refs: Vec<&Segment> = seg_indices.iter().map(|&i| &all_segments[i]).collect();
            generate_tile(zoom, *tx, *ty, &seg_refs);
            pb.inc(1);
        });
        pb.finish();
    }

    println!("Total execution time: {:.2?}s", start_time.elapsed());
}