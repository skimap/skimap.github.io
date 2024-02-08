# extract the coordinates of the end points of the ski lifts from the lifts.geojson file

import json
import pandas as pd

# read the lifts.geojson file
lifts = pd.read_json("lifts.geojson")
newjs_s = []
newjs_e = []

# identify the end points of the ski lifts depending on the types of the coordinates
for i in range(len(lifts["features"])):
    if isinstance(lifts["features"][i]["geometry"]["coordinates"][-1], (float, int)):
        newjs_s.append(lifts["features"][i]["geometry"]["coordinates"][:2])
        newjs_e.append(lifts["features"][i]["geometry"]["coordinates"][:2])
    elif isinstance(lifts["features"][i]["geometry"]["coordinates"][-1][-1], (float, int)):
        newjs_s.append(lifts["features"][i]["geometry"]["coordinates"][0][:2])
        newjs_e.append(lifts["features"][i]["geometry"]["coordinates"][-1][:2])
    elif isinstance(lifts["features"][i]["geometry"]["coordinates"][0], list):
        newjs_s.append(lifts["features"][i]["geometry"]["coordinates"][0][0][:2])
        newjs_e.append(lifts["features"][i]["geometry"]["coordinates"][0][-1][:2])
    else: 
        newjs_s.append(lifts["features"][i]["geometry"]["coordinates"][:2])
        newjs_e.append(lifts["features"][i]["geometry"]["coordinates"][:2])
        print(lifts["features"][i]["geometry"]["coordinates"])
    print(i)
    

# save the coordinates of the starting points of the ski lifts to a json file
with open('lifts_s.json', 'w') as file:
    json.dump(newjs_s, file)
# save the coordinates of the end points of the ski lifts to a json file
with open('lifts_e.json', 'w') as file:
    json.dump(newjs_e, file)