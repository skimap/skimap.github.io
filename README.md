# Skimap.github.io

This project processes ski track data (GPX) and renders them onto a map using a modern React frontend and a Rust-based tile renderer.

## Prerequisites

- **Python 3.x**
- **Node.js & npm**
- **Rust** (for the tile renderer)

## Getting Started

### 1. Setup

Install Python dependencies:

Windows:
```bash
pip install -r requirements.txt
```
Mac / Linux:
```bash
pip3 install -r requirements.txt
```

Install Frontend dependencies:
```bash
cd frontend
npm install
cd ..
```

Build the Rust Renderer:
```bash
cd ski_renderer
cargo build --release
cd ..
```

### 2. Generate Data & Tiles

Run the pipeline to process GPX files, generate tiles, and output the data for the frontend:

```bash
python3 merge.py
```
*Note: Use `--html-only` to skip tile generation if you only updated the logic or data extraction.*

### 3. Run the Application

**Development (Hot Reloading):**
Start the Vite dev server:
```bash
cd frontend
npm run dev
```
Open `http://localhost:5173` (or whatever port you are presented).

**Production Build:**
Build the static site:
```bash
cd frontend
npm run build
```
The output will be in `frontend/dist`. You can serve this folder with any static file server.

## Architecture

- **Data Processing (`merge.py`):** 
    - Merges GPX files.
    - Identifies ski areas.
    - outputs `frontend/public/map_data.json`.
- **Tile Rendering (`ski_renderer/`):** 
    - Rust application that renders GPX tracks into PNG tiles.
    - Tiles are stored in `frontend/public/tiles/`.
- **Frontend (`frontend/`):**
    - **Vite + React + TypeScript** application.
    - **Tailwind CSS** for styling.
    - **React Leaflet** for the map.
    - **React Select** for the searchable dropdown.

## Project Structure

- `frontend/`: React application source.
- `frontend/public/tiles/`: Generated map tiles.
- `ski_renderer/`: Rust tile renderer source.
- `tracks/`: Raw GPX data.
- `json/`: Ski area and lift databases.
