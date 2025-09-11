# Define color based on moving average descent rate

# coloring scheme
# 1: green/blue/red/black
# 2: light green/dark green/light blue/dark blue/purple/red/black
# 3: same as 2, but with correct % calculation to max percent 56% (EU)
# 4: same as 2, but with correct % calculation to max percent 45% (HU)

# TODO allow the user to switch between the colours

import numpy as np

def get_color(rate: float, coloring_scheme: int):
    if coloring_scheme == 1:
        if rate >= 0:
            return '#80808020'
        elif rate >= -0.15:
            return 'green'
        elif rate >= -0.29:
            return 'blue'
        elif rate >= -0.45:
            return 'red'
        else:
            return 'black'
    if coloring_scheme == 2:
        if rate >= 0:
            return '#80808080'
        elif rate >= -0.07:
            return '#48B748'    # light green
        elif rate >= -0.15:
            return '#006400'     # dark green
        elif rate >= -0.20:
            return '#32A2D9'     # light blue
        elif rate >= -0.25:
            return '#0000FF'     # blue
        elif rate >= -0.3:
            return '#800080'     # purple
        elif rate >= -0.37:
            return 'red'
        elif rate >= -0.45:
            return 'darkred'
        else:
            return 'black'
    if coloring_scheme == 3:    # 100% is 56°, European colors
        alpha = np.arctan(rate)*2/np.pi*90
        ski_slope_rate = alpha / 56
        if ski_slope_rate >= 0:
            return '#80808080'
        elif ski_slope_rate >= -0.07:
            return '#48B748'    # light green
        elif ski_slope_rate >= -0.15:
            return '#006400'     # dark green
        elif ski_slope_rate >= -0.20:
            return '#32A2D9'     # light blue
        elif ski_slope_rate >= -0.25:
            return '#0000FF'     # blue
        elif ski_slope_rate >= -0.3:
            return '#800080'     # purple
        elif ski_slope_rate >= -0.37:
            return 'red'
        elif ski_slope_rate >= -0.45:
            return 'darkred'
        else:
            return 'black'
    if coloring_scheme == 4:    # 100% is 45°, Hungarian colors
        alpha = np.arctan(rate)*2/np.pi*90
        ski_slope_rate = alpha / 45
        if ski_slope_rate >= 0:
            return '#80808080'
        elif ski_slope_rate >= -0.07:
            return '#48B748'    # light green
        elif ski_slope_rate >= -0.15:
            return '#006400'     # dark green
        elif ski_slope_rate >= -0.20:
            return '#32A2D9'     # light blue
        elif ski_slope_rate >= -0.25:
            return '#0000FF'     # blue
        elif ski_slope_rate >= -0.3:
            return '#800080'     # purple
        elif ski_slope_rate >= -0.37:
            return 'red'
        elif ski_slope_rate >= -0.45:
            return 'darkred'
        else:
            return 'black'
