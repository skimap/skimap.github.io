import os
import webbrowser

# Directories
base_dir = "c:/zselyigy/dev/skimap/"
html_directory = f"{base_dir}htmls/splitted_slides/"     # Htmls to be revised
track_directory = f"{base_dir}tracks/tracks_to_split/splitted_slides/"     # Tracks to be revised

while True:
    for filename in os.listdir(html_directory):
        if filename.endswith(".html"):
            webbrowser.open_new_tab(f"{html_directory + filename}")
            if input("Correct track? Y/Enter key") == "Y":
                pass
            else:
                os.remove(f"{html_directory + filename}")
                os.remove(f"{track_directory + filename[:-5]}.gpx")
    break