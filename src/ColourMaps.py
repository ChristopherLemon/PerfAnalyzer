
cluster_plot_colours = ('#F44336', '#3F51B5', '#009688', '#FFC107', '#FF5722', '#9C27B0', '#03A9F4', '#8BC34A',
                        '#FF9800', '#E91E63', '#2196F3', '#4CAF50', '#FFEB3B', '#673AB7', '#00BCD4', '#CDDC39',
                        '#9E9E9E', '#607D8B')

distinct_colours = [(2, 63, 165), (125, 135, 185), (190, 193, 212), (214, 188, 192), (187, 119, 132), (142, 6, 59),
                    (74, 111, 227), (133, 149, 225), (181, 187, 227), (230, 175, 185), (224, 123, 145), (211, 63, 106),
                    (17, 198, 56), (141, 213, 147), (198, 222, 199), (234, 211, 198), (240, 185, 141), (239, 151, 8),
                    (15, 207, 192), (156, 222, 214), (213, 234, 231), (243, 225, 235), (246, 196, 225), (247, 156, 212)]

min_max_colours = ('#0052A5', '#00753A', '#B21F35', '#06A9FC', '#009E47', '#FF7435')

top_ten = ('#B21F35', '#D82735', '#FF7435', '#FFA135', '#FFCB35', '#FFF735', '#16DD36', '#009E47', '#00753A',
           '#0052A5', '#0079E7', '#06A9FC')


def get_gradient_colours(n_pos, n_neg, return_hex=True):
    """Return discrete set of graduated colours for positive/negative values.
    Partitions red colour gradient into positive range, and blue coulour
    gradient into negative range."""
    n = n_pos
    r = 255
    dn = 210 // (n - 1)
    colours = []
    for i in range(n):
        g = i * dn
        b = i * dn
        colours.append((r, g, b))
    n = n_neg
    b = 255
    for i in range(n):
        r = i * dn
        g = i * dn
        colours.append((r, g, b))
    if return_hex:
        c = [rgb2hex(colours[i][0], colours[i][1], colours[i][2]) for i in
             range(0, len(colours))]
    else:
        c = colours
    return c


def rgb2hex(r, g, b):
    """Convert rgb colour to hex colour"""
    c = "#{:02x}{:02x}{:02x}".format(r, g, b)
    return c


def hex2rgb(hexcode):
    """Convert hex colour to rgb colour"""
    c = (int(hexcode[1:3], 16), int(hexcode[3:5], 16), int(hexcode[5:7], 16))
    return "rgb" + str(c)


def get_cluster_plot_colours(return_hex=True):
    """Return set of distinct colours for use in cluster groupings"""
    if return_hex:
        c = cluster_plot_colours
    else:
        c = [hex2rgb(cluster_plot_colours[i]) for i in range(0, len(cluster_plot_colours))]
    return c


def get_top_ten_colours(return_hex=True):
    """Return gradient through red, green, and blue. Actually returns list of 12 colours!"""
    if return_hex:
        c = top_ten
    else:
        c = [hex2rgb(top_ten[i]) for i in range(0, len(top_ten))]
    return c


def get_distinct_colours(return_hex=True):
    """Return large set of distinct colours for use in cluster groupings"""
    if return_hex:
        c = [rgb2hex(distinct_colours[i][0], distinct_colours[i][1], distinct_colours[i][2]) for i in
             range(0, len(distinct_colours))]
    else:
        c = distinct_colours
    return c
