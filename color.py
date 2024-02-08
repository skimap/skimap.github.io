# Define color based on moving average descent rate
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
