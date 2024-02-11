# transforms openskimap runs using 'mapping table.csv' to ref_points.json,
# creates htmls and displays
import json
import sys

# read 'mapping table.csv'
with open('json/slopes/slope mapping table.csv') as file:
    for line in file:
        print(line)
        run_points = []
        line_parts = line.split(';')
        # get the filename of the ski area
        filename = line_parts[0]
        with open(f'json/slopes/raw/{filename}.json', encoding='utf-8') as f:
            runs = json.load(f)
        # get the slope id
        id = line_parts[1]
        # compose the ref points of the slopes from the runs according to the mapping table
        line_parts[2].replace('\n', '')
        slope_parts = line_parts[2][2:-3].split('],[')
        for mypart in slope_parts:
            ps = mypart.split(',')
            raw_track_no = int(ps[0])
            if len(ps) == 2:
                if ps[1] != "'all'":
                    sys.exit('Fatal error in the slope mapping table!')
                else:
                    startindex = 0
                    endindex = len(runs["items"][0]["tracks"][raw_track_no]["points"])-1
            elif len(ps) == 3:
                startindex = ps[1]
                endindex = ps[2]
            else:
                sys.exit('Fatal error in the slope mapping table!')
                    

            print(mypart[0], startindex, endindex)
        