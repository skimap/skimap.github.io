# extract the coordinates of the end points of the ski lifts from the lifts.geojson file

import json
import pandas as pd

# read the lifts.geojson file
lifts = pd.read_json("lifts.geojson")
newjs = []

# identify the end points of the ski lifts depending on the types of the coordinates
for i in range(len(lifts["features"])):
    if isinstance(lifts["features"][i]["geometry"]["coordinates"][-1], (float, int)):
        newjs.append(lifts["features"][i]["geometry"]["coordinates"])
    elif isinstance(lifts["features"][i]["geometry"]["coordinates"][-1][-1], (float, int)):
        newjs.append(lifts["features"][i]["geometry"]["coordinates"][-1])
    elif isinstance(lifts["features"][i]["geometry"]["coordinates"][0], list):
        newjs.append(lifts["features"][i]["geometry"]["coordinates"][0][-1])
    else: 
        newjs.append(lifts["features"][i]["geometry"]["coordinates"])
        print(lifts["features"][i]["geometry"]["coordinates"])
    print(i)
    
# save the coordinates of the end points of the ski lifts to a json file
with open('lifts.json', 'w') as file:
    json.dump(newjs, file)