# Skimap.github.io

This project processes ski track data (GPX) and renders them onto a map. it includes a Python-based processing pipeline and a high-performance Rust-based tile renderer.

## Prerequisites

- **Python 3.x**
- **Rust** (for the tile renderer)

## Getting Started

### 1. Python Environment Setup

Install the required Python dependencies:

Windows:
```bash
pip install -r requirements.txt
```
Mac / Linux:
```bash
pip3 install -r requirements.txt
```

### 2. Rust Tile Renderer

The Rust renderer is located in the `ski_renderer` directory. It processes GPX files from `tracks/raw/all` and generates map tiles in the `tiles` directory.

To build and run the renderer:

```bash
cd ski_renderer
cargo run --release
```

### 3. Running the Web Interface

The project is a static website. You can serve it using any local web server. For example, using Python:

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000` in your browser.