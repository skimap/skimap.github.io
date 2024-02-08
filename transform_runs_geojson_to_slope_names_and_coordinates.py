# extract the coordinates of the end points of the ski runs from the runs.geojson file
import json

# Directories
base_dir = "C:/zselyigy/dev/skimap/"

# read the runs.geojson file
with open("runs.geojson", 'r', encoding='utf-8') as file:
    runs = json.load(file)
print('runs.geojson file read.')



items = []
# identify the end points of the ski runs depending on the types of the coordinates
for i in range(len(runs["features"])):
    if runs["features"][i]["properties"]["uses"][0] == "downhill":
        if runs["features"][i]["properties"]["skiAreas"][0]["properties"]["name"] == "Sípark Mátraszentistván":
            # collect the slope coordinates
            points = []
            mytrack = []
            for j in range(len(runs["features"][i]["geometry"]["coordinates"][0])):
                points.append({"lat": runs["features"][i]["geometry"]["coordinates"][0][1][1], "lon": runs["features"][i]["geometry"]["coordinates"][0][1][0]})
            # Append a dictionary with trackname and points keys to the tracks list
            mytrack.append({"trackname": runs["features"][i]["properties"]["name"] , "points": points})
            # Append a dictionary with name and tracks keys to the items list
            items.append({"name": runs["features"][i]["properties"]["skiAreas"][0]["properties"]["name"], "tracks": mytrack})
        print(i)

# Create the JSON structure
json_data = {"items": items}
    
# save the coordinates of the starting points of the ski lifts to a json file
with open('newslopes.json', 'w') as file:
    json.dump(json_data, file, indent=4)