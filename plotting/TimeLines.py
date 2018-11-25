import os
import re
import string
import sys
from collections import OrderedDict, namedtuple
from tools.Utilities import natural_sort
from plotting.ColourMaps import cluster_plot_colours

def get_svg_scripts(xpad, bgcolor1, bgcolor2, nametype, fontsize, fontwidth, searchcolor):
    values = {'xpad': xpad, 'bgcolor1': bgcolor1, 'bgcolor2': bgcolor2, 'nametype': nametype,
              'fontsize': fontsize, 'fontwidth': fontwidth, 'searchcolor': searchcolor}

    svg_scripts = string.Template("""<defs >
    <linearGradient id="background" y1="0" y2="1" x1="0" x2="0" >
        <stop stop-color="$bgcolor1" stop-opacity="0.0" offset="5%" />
        <stop stop-color="$bgcolor1" stop-opacity="1.0" offset="15%" />
        <stop stop-color="$bgcolor2" stop-opacity="1.0" offset="100%" />
    </linearGradient>
</defs>
<style type="text/css">
    .func_g:hover { stroke:black; stroke-width:0.5; cursor:pointer; }
</style>
<script type="text/ecmascript">
<![CDATA[
    var details, svg, globalscale;
    document.search = search;
    document.reset_search = reset_search;
    function init(evt) {
        details = document.getElementById("details").firstChild;
        searching = 0;
    }

    // mouse-over for info
    function s(node) {      // show
        info = g_to_text(node);
        details.nodeValue = "$nametype " + info;
    }
    function c() {          // clear
        details.nodeValue = ' ';
    }
    function orig_save(e, attr, val) {
        if (e.attributes["_orig_"+attr] != undefined) return;
        if (e.attributes[attr] == undefined) return;
        if (val == undefined) val = e.attributes[attr].value;
        e.setAttribute("_orig_"+attr, val);
    }
    function orig_load(e, attr) {
        if (e.attributes["_orig_"+attr] == undefined) return;
        e.attributes[attr].value = e.attributes["_orig_"+attr].value;
        e.removeAttribute("_orig_"+attr);
    }
    function g_to_text(e) {
        var text = find_child(e, "title").firstChild.nodeValue;
        return (text)
    }
    function g_to_func(e) {
        var func = g_to_text(e);
        if (func != null)
            func = func.replace(/.* Max: /, "");
            func = func.replace(/ .*/, "");
        return (func);
    }
    function find_child(parent, name, attr) {
        var children = parent.childNodes;
        for (var i=0; i<children.length;i++) {
            if (children[i].tagName == name)
                return (attr != undefined) ? children[i].attributes[attr].value : children[i];
        }
        return;
    }
    function reset_search() {
        var el = document.getElementsByTagName("rect");
        for (var i=0; i < el.length; i++) {
            orig_load(el[i], "fill")
        }
    }
    function search(term) {
        var re = new RegExp(term);
        var el = document.getElementsByTagName("g");
        var maxwidth = 0;
        for (var i = 0; i < el.length; i++) {
            var e = el[i];
            if (e.attributes["class"].value != "func_g")
                continue;
            var func = g_to_func(e);
            var rect = find_child(e, "rect");
            if (rect == null) {
                // the rect might be wrapped in an anchor
                // if nameattr href is being used
                if (rect = find_child(e, "a")) {
                    rect = find_child(r, "rect");
                }
            }
            if (func == null || rect == null)
                continue;

            // Save max width. Only works as we have a root frame
            var w = parseFloat(rect.attributes["width"].value);
            if (w > maxwidth)
                maxwidth = w;

            if (func.match(re)) {
                // highlight
                var x = parseFloat(rect.attributes["x"].value);
                orig_save(rect, "fill");
                rect.attributes["fill"].value =
                    "$searchcolor";
                searching = 1;
            }
        }
        if (!searching)
            return;
    }
]]>
</script>""")
    return svg_scripts.substitute(values)

class Attributes:

    def __init__(self, info):
        self.attributes = {'class': "\"func_g\"",
                           'onmouseover': "\"s(this)\"",
                           'onmouseout': "\"c()\"",
                           'title': info}

class SVGPackage:

    def __init__(self):
        self.svg = []

    def header(self, width, height):
        values = {'width': width, 'height': height}
        svg_header = string.Template("""<?xml version="1.0" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg version="1.1" width="100%" height="100%" onload="init(evt)" viewBox="0 0 $width $height" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<!-- Flame graph stack visualization. See https://github.com/brendangregg/FlameGraph for latest version, and http://www.brendangregg.com/flamegraphs.html for examples. -->""")
        self.svg.append(svg_header.substitute(values) + "\n")

    def include(self, content):
        self.svg.append(content + "\n")

    def colorAllocate(self, r, g, b):
        return "rgb({},{},{})".format(r, g, b)

    def group_start(self, attr):
        g_attributes = "<g class={} onmouseover={} onmouseout={}>\n".format(attr.attributes["class"],
                                                                            attr.attributes["onmouseover"],
                                                                            attr.attributes["onmouseout"])
        self.svg.append(g_attributes)
        self.svg.append("<title>{}</title>".format(attr.attributes["title"]))

    def group_end(self, attr):
        self.svg.append("</g>\n")

    def filled_rectangle(self, x1, y1, x2, y2, fill, extra = ""):
        x1 = '{:.1f}'.format(x1)
        x2 = '{:.1f}'.format(x2)
        w = '{:.1f}'.format(float(x2) - float(x1))
        h = '{:.1f}'.format(float(y2) - float(y1))
        values = {'x1': x1, 'y1': y1, 'w': w, 'h': h, 'fill': fill, 'extra': extra}
        rectangle = string.Template("""<rect x="$x1" y="$y1" width="$w" height="$h" fill="$fill" $extra/>\n""")
        self.svg.append(rectangle.substitute(values))

    def stringTTF(self, color, font, size, x, y, str, loc="left", extra=""):
        x = '{:.2f}'.format(x)
        values = {'loc': loc, 'x': x, 'y': y, 'size': size, 'font': font, 'color': color, 'str': str, 'extra': extra}
        string_ttf = string.Template("""<text text-anchor="$loc" x="$x" y="$y" font-size="$size" font-family="$font" fill="$color" $extra >$str</text>\n""")
        self.svg.append(string_ttf.substitute(values))

    def polyline(self, path_coords, extra=""):
        self.svg.append("<polyline points=\"")
        for x, y in path_coords:
            xi = '{:.1f}'.format(x)
            yi = '{:.1f}'.format(y)
            self.svg.append(xi + "," + yi + " ")
        self.svg.append("\" fill=\"transparent\" stroke-opacity=\"0.8\" stroke=\"grey\" stroke-width=\"2\" " + extra + "/>\n")

    def line(self, x1, y1, x2, y2, extra=""):
        x1 = '{:.1f}'.format(x1)
        x2 = '{:.1f}'.format(x2)
        y1 = '{:.1f}'.format(y1)
        y2 = '{:.1f}'.format(y2)
        values = {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'extra': extra}
        rectangle = string.Template("""<line x1="$x1" y1="$y1" x2="$x2" y2="$y2" $extra stroke-opacity=\"0.8\" stroke=\"grey\" stroke-width=\"2\"/>\n""")
        self.svg.append(rectangle.substitute(values))

    def get_svg(self):
        self.svg.append("</svg>\n")
        return "".join(self.svg)

class ColorHandler:

    def __init__(self):
        self.palette_map = {}

    def color(self, type, name):
        v1 = self.namehash(name)
        if type:
            if type == "aqua":
                r = 50 + int(60 * v1)
                g = 165 + int(55 * v1)
                b = 165 + int(55 * v1)
                return "rgb({},{},{})".format(str(r),str(g),str(b))

    def read_palette(self, palette_file):
        if os.path.isfile(palette_file):
            fin = open(palette_file, 'r')
            for line in fin:
                map = line.strip().split("->")
                self.palette_map[map[0]] = map[1]
            fin.close()

    def color_map(self, type, func):
        if func in self.palette_map:
            return self.palette_map[func]
        else:
            self.palette_map[func] = self.color(type,func)
            return self.palette_map[func]

    def namehash(self,name):
        vector = 0
        weight = 1
        max = 1
        mod = 10
        name = re.sub(r'.(.*?)`/','',name)
        for c in list(name):
            i = (ord(c)) % mod
            vector += (i / (mod - 1)) * weight
            mod += 1
            max += weight
            weight *= 0.7
            if mod > 12:
                break
        return (1 - vector / max)

ImageSettings = namedtuple('defaults',
                          ['imagewidth',
                           'frameheight',
                           'fontsize',
                           'fontwidth',
                           'fonttype',
                           'minwidth',
                           'xpad',
                           'ypad1',
                           'ypad2',
                           'framepad',
                           'bgcolor1',
                           'bgcolor2',
                           'nametype',
                           'searchcolor',
                           'pal_file',
                           'colors'])


def precision(t, range):
    if range < 1.0:
        return '{:.4f}'.format(t)
    elif range < 100.0:
        return '{:.2f}'.format(t)
    else:
        return '{:.0f}'.format(t)

class TimeLines:

    def __init__(self, working_dir, in_file, out_file, intervals,
                 color_map=None,
                 has_color_map=False,
                 imagewidth=1200,
                 frameheight=16,
                 fontsize=12,
                 fontwidth=0.59,
                 fonttype='Verdana',
                 minwidth=0.1,
                 nametype='Function',
                 searchcolor='rgb(230,0,230)',
                 pal_file='palette.map',
                 colors='aqua'):
        self.working_dir = working_dir
        self.in_file = self.working_dir + os.sep + in_file
        self.out_file = self.working_dir + os.sep + out_file
        self.has_color_map = has_color_map
        self.data = []
        self.nlevels = 0
        self.timelines = OrderedDict()
        self.sample_rates = OrderedDict()
        self.secondary_events = OrderedDict()
        self.max_sample_rate = 0.0
        self.color_handler = ColorHandler()
        self.intervals = intervals
        if color_map:
            self.color_handler.palette_map = color_map
        self.read_data()
        self.im = SVGPackage()
        self.image_settings = self.set_image_setings(fontsize, imagewidth, frameheight, fontwidth, fonttype, minwidth,
                                                     nametype, searchcolor, pal_file, colors)
        self.svg_scripts = self.set_svg_scripts()
        self.process_stacks()


    def set_image_setings(self, fontsize, imagewidth, frameheight, fontwidth, fonttype, minwidth,
                          nametype, searchcolor, pal_file, colors):
        bgcolor1 = '#f8f8f8'
        bgcolor2 = '#e8e8e8'
        return ImageSettings(imagewidth=imagewidth,
                             frameheight=frameheight,
                             fontsize=fontsize,
                             fontwidth=fontwidth,
                             fonttype=fonttype,
                             minwidth=minwidth,
                             xpad=10,
                             ypad1=fontsize * 4,
                             ypad2=fontsize * 2 + 10,
                             framepad=1,
                             bgcolor1=bgcolor1,
                             bgcolor2=bgcolor2,
                             nametype=nametype,
                             searchcolor=searchcolor,
                             pal_file=pal_file,
                             colors=colors)

    def set_svg_scripts(self):
        xpad = self.image_settings.xpad
        bgcolor1 = self.image_settings.bgcolor1
        bgcolor2 = self.image_settings.bgcolor2
        nametype = self.image_settings.nametype
        fontsize = self.image_settings.fontsize
        fontwidth = self.image_settings.fontwidth
        searchcolor = self.image_settings.searchcolor
        return get_svg_scripts(xpad, bgcolor1, bgcolor2, nametype, fontsize, fontwidth, searchcolor)

    def read_data(self):
        fin = open(self.in_file, 'r')
        for line in fin:
            self.data.append(line)
        fin.close()

    def process_stacks(self):
        process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
        for line in self.data:
            line = line.strip()
            if re.search("secondary-event", line):
                match = re.search(process_id_regex, line)
                if match:
                    pid = match.group(2)
                    tid = match.group(3)
                    match2 = re.match("secondary-event;(.*)\s+(.*)\s+(.*)", line)
                    if match2:
                        line, par, time = line.rpartition(' ')
                        event = line.rpartition(' ')[2]
                        if pid not in self.secondary_events:
                            self.secondary_events[pid] = OrderedDict()
                        if tid not in self.secondary_events[pid]:
                            self.secondary_events[pid][tid] = []
                        self.secondary_events[pid][tid].append((event, float(time)))
            elif re.search("sample-rate", line):
                match = re.search(process_id_regex, line)
                if match:
                    pid = match.group(2)
                    tid = match.group(3)
                    if pid not in self.sample_rates:
                        self.sample_rates[pid] = OrderedDict()
                    if tid not in self.sample_rates[pid]:
                        self.sample_rates[pid][tid] = []
                    line, par, rate = line.rpartition(' ')
                    time = line.rpartition(' ')[2]
                    self.sample_rates[pid][tid].append((float(time), float(rate)))
                    self.max_sample_rate = max(self.max_sample_rate, float(rate))
            else:
                match = re.search(process_id_regex, line)
                if match:
                    pid = match.group(2)
                    tid = match.group(3)
                    if pid not in self.timelines:
                        self.timelines[pid] = OrderedDict()
                    if tid not in self.timelines[pid]:
                        self.timelines[pid][tid] = []
                        self.nlevels += 1
                    line, par, count = line.rpartition(' ')
                    line, par, end = line.rpartition(' ')
                    line, par, start = line.rpartition(' ')
                    func = line.rpartition(";")[2]
                    if func:
                        self.timelines[pid][tid].append((func, start, end, int(count)))
        self.make_svg()

    def make_svg(self):
        imagewidth = self.image_settings.imagewidth
        frameheight = self.image_settings.frameheight
        fonttype = self.image_settings.fonttype
        fontsize = self.image_settings.fontsize
        fontwidth = self.image_settings.fontwidth
        xpad = self.image_settings.xpad
        ypad1 = self.image_settings.ypad1
        ypad2 = self.image_settings.ypad2
        framepad = self.image_settings.framepad
        imageheight = self.nlevels * (frameheight + 2 * framepad) + ypad1 + ypad2
        widthpertime = float(imagewidth - 2 * xpad) / float(self.intervals)
        self.min_time = sys.maxsize
        self.max_time = -sys.maxsize
        scale_time = float(imagewidth - 2 * xpad)
        self.im.header(imagewidth, imageheight)
        self.im.include(self.svg_scripts)
        self.im.filled_rectangle(0, 0, imagewidth, imageheight, 'transparent', extra="id=\"background_rect\"")
        black = self.im.colorAllocate(0, 0, 0)
        self.im.stringTTF(black, fonttype, fontsize, xpad, imageheight - (ypad2 / 2), " ", "",
                          "id=\"details\"")
        y1 = ypad1
        for pid in natural_sort(self.timelines.keys()):
            for tid in natural_sort(self.timelines[pid].keys()):
                y2 = y1 + frameheight
                x1 = xpad
                for func, start, end, count in self.timelines[pid][tid]:
                    self.min_time = min(self.min_time, float(start))
                    self.max_time = max(self.max_time, float(end))
                    escaped_func = re.sub("&", "&amp;", func)
                    escaped_func = re.sub("<", "&lt;", escaped_func)
                    escaped_func = re.sub(">", "&gt;", escaped_func)
                    escaped_func = re.sub("\"", "&quot;", escaped_func)
                    start = '{:.6f}'.format(float(start))
                    end = '{:.6f}'.format(float(end))
                    info = "pid:{}-tid:{} Max: {} (Start: {}, End: {})".format(str(pid), str(tid), escaped_func, start, end)
                    nameattr = Attributes(info)
                    self.im.group_start(nameattr)
                    color = self.color_handler.color_map(self.image_settings.colors, func)
                    x2 = x1 + count * widthpertime
                    self.im.filled_rectangle(x1, y1, x2, y2, color, "rx=\"2\" ry=\"2\"")
                    self.im.group_end(nameattr)
                    x1 = x2
                y1 += frameheight + 2 * framepad
        scale_time /= (self.max_time - self.min_time)

        x1 = xpad
        y1 = float(ypad1) / 2.0
        count = 0
        n_ticks = self.intervals / 10
        for pid in sorted(self.timelines.keys()):
            for tid in sorted(self.timelines[pid].keys()):
                dt = self.sample_rates[pid][tid][1][0] - self.sample_rates[pid][tid][0][0]
                t = self.sample_rates[pid][tid][0][0] - 0.5 * dt
                range = self.sample_rates[pid][tid][-1][0] - self.sample_rates[pid][tid][0][0]
                for time, rate in self.sample_rates[pid][tid]:
                    t1 = precision(t, range)
                    if count % n_ticks == 0:
                        y2 = y1 - (float(ypad1) / 8.0)
                        self.im.line(x1, y1, x1, y2, extra="class=\"time_interval\" title=\"" + t1 + "\"")
                        if count == 0:
                            loc = "start"
                        else:
                            loc = "middle"
                        self.im.stringTTF(black, fonttype, fontsize - 2, x1, y2 + 1, t1, loc=loc, extra="font-style=\"italic\"")
                    else:
                        y2 = y1 - (float(ypad1) / 16.0)
                        self.im.line(x1, y1, x1, y2, extra="class=\"time_interval\" title=\"" + t1 + "\"")
                    x1 += widthpertime
                    t += dt
                    count += 1
                break
            break
        t1 = precision(t, range)
        y2 = y1 - (float(ypad1) / 8.0)
        loc = "end"
        self.im.stringTTF(black, fonttype, fontsize - 2, x1, y2 + 1, t1, loc=loc)
        self.im.line(x1, y1, x1, y2, extra="class=\"time_interval\" title=\"" + t1 + "\"")
        self.im.line(xpad, y1, x1, y1)

        y1 = ypad1
        for pid in sorted(self.sample_rates.keys()):
            for tid in sorted(self.sample_rates[pid].keys()):
                x1 = xpad
                path_coords = []
                for time, rate in self.sample_rates[pid][tid]:
                    norm_rate = 0.0
                    if self.max_sample_rate > 0.0:
                        norm_rate = rate / self.max_sample_rate
                    xi = x1 + 0.5 * widthpertime
                    yi = y1 + (1.0 - norm_rate) * frameheight
                    path_coords.append((xi, yi))
                    x1 += widthpertime
                self.im.polyline(path_coords)
                y1 += frameheight + 2 * framepad

        y1 = ypad1
        colors = {}
        for pid in sorted(self.secondary_events.keys()):
            for tid in sorted(self.secondary_events[pid].keys()):
                x1 = xpad
                for event, time in self.secondary_events[pid][tid]:
                    xi = x1 + (time - self.min_time) * scale_time
                    yi = y1
                    xj = xi + 3
                    yj = yi + frameheight
                    if event not in colors:
                        nc = len(colors)
                        colors[event] = cluster_plot_colours[nc]
                    color = colors[event]
                    t = '{:.6f}'.format(float(time))
                    nameattr = Attributes(event + " " + t)
                    self.im.group_start(nameattr)
                    self.im.filled_rectangle(xi, yi, xj, yj, color, "rx=\"0\" ry=\"0\"")
                    self.im.group_end(nameattr)
                y1 += frameheight + 2 * framepad

        self.write_timelines()


    def write_timelines(self):
        f = open(self.out_file, 'w')
        f.write(self.im.get_svg())
        f.close()

