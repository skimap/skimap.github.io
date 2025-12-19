import subprocess
import sys

print("Step 1: Running High-Performance Rust Renderer...")
try:
    # Calls the compiled Rust binary
    result = subprocess.run(["./ski_renderer/target/release/ski_renderer.exe"], check=True)
except subprocess.CalledProcessError:
    print("Rust renderer failed!")
    sys.exit(1)