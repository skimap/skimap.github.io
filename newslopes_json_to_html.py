import json
import os

# Directories
base_dir = "C:/zselyigy/dev/skimap/"
html_directory = base_dir + "htmls/"

def save_track_to_html(filename, latitude, longitude):
    import folium
    # create a map centered at mid Europe with a zoom level of 15
    mymap = folium.Map(location=[latitude[0], longitude[0]], zoom_start=16)
    title_html = f'<h3 align="center" style="font-size:16px" >{filename}</h3>'
    mymap.get_root().html.add_child(folium.Element(title_html))


    for i in range(len(latitude) - 1):
            folium.PolyLine(
            locations=[[latitude[i], longitude[i]], [latitude[i + 1], longitude[i + 1]]], weight=6, color='black').add_to(mymap)
            # add markers to make the points easier to see
            folium.Marker([latitude[i], longitude[i]], icon= folium.Icon(color='blue', icon='star')).add_to(mymap)


    # Save the map as an HTML file
    html_content = mymap.get_root().render()

    # Write the modified HTML content to a file
    with open(os.path.join(html_directory, f"{filename}.html"), "w", encoding="utf-8") as html_file:
        html_file.write(html_content)
        

json_filename = "Matraszentistvan"        
# read the slope coordinates from the newslopes.json file
with open(f"{json_filename}.json", 'r', encoding='utf-8') as file:
    runs = json.load(file)

for i, track in enumerate(runs["items"][0]["tracks"]):
    filename = f'{json_filename}_slopeNo_{i}_id_{track["trackname"]}'
    lat = []
    lon = []
    for point in track["points"]:
        lat.append(point["lat"])
        lon.append(point["lon"])
    save_track_to_html(filename, lat, lon)
    print(f'{filename} was saved.')
