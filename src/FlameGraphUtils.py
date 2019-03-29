# Python version of flamegraphs transcribed from flamegraph.pl by Brendan Gregg. Contains the
# subset of functionality required for displaying standard flamecharts and difference plots. Also
# contains modifications to display stack ordering in time order,
# retain exclusive (as well as inclusive) sample counts, and to plot ratios of perf events
import string
import re
import sys
import math
import os
from functools import cmp_to_key
from collections import namedtuple
from decimal import Decimal


def format_number(x):
    y = float(x)
    if abs(y) >= 1000.0:
        y = '{0:.2E}'.format(Decimal(x))
    else:
        y = str(x)
    return y


def get_svg_scripts(xpad, bgcolor1, bgcolor2, nametype, fontsize, fontwidth, inverted, searchcolor):
    # Scripts to be copied into svg file
    values = {'xpad': xpad, 'bgcolor1': bgcolor1, 'bgcolor2': bgcolor2, 'nametype': nametype,
              'fontsize': fontsize, 'fontwidth': fontwidth, 'inverted': inverted, 'searchcolor': searchcolor}

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
    var details, searchbtn, matchedtxt, svg, globalscale;
    document.search = search;
    document.reset_search = reset_search;
    document.zoom = zoom;
    function init() {
        details = document.getElementById("details").firstChild;
        searchbtn = document.getElementById("search");
        matchedtxt = document.getElementById("matched");
        svg = document.getElementsByTagName("svg")[0];
        globalscale = svg.viewBox.baseVal.width/svg.width.baseVal.value;
        searching = 0;
    }
    function resize() {
        svg = document.getElementsByTagName("svg")[0];
        globalscale = svg.viewBox.baseVal.width/svg.width.baseVal.value;
    }

    // mouse-over for info
    function s(node) {      // show
        info = g_to_text(node);
        details.nodeValue = "$nametype " + info;
    }
    function c() {          // clear
        details.nodeValue = ' ';
    }

    // ctrl-F for search
    window.addEventListener("keydown",function (e) {
        if (e.keyCode === 114 || (e.ctrlKey && e.keyCode === 70)) {
            e.preventDefault();
            search_prompt();
        }
    })

    // functions
    function find_child(parent, name, attr) {
        var children = parent.childNodes;
        for (var i=0; i<children.length;i++) {
            if (children[i].tagName == name)
                return (attr != undefined) ? children[i].attributes[attr].value : children[i];
        }
        return;
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
            func = func.replace(/ .*/, "");
        return (func);
    }
    function update_text(e) {
        var r = find_child(e, "rect");
        var t = find_child(e, "text");
        var w = parseFloat(r.attributes["width"].value) -3;
        var txt = find_child(e, "title").textContent.replace(/\\([^(]*\\)$$/,"");
        t.attributes["x"].value = parseFloat(r.attributes["x"].value) +3;

        // Smaller than this size won't fit anything
        if (w < 2*$fontsize*$fontwidth) {
            t.textContent = "";
            return;
        }

        t.textContent = txt;
        // Fit in full text width
        if (/^ *$$/.test(txt) || t.getSubStringLength(0, txt.length) < w)
            return;

        for (var x=txt.length-2; x>0; x--) {
            if (t.getSubStringLength(0, x+2) <= w) {
                t.textContent = txt.substring(0,x) + "..";
                return;
            }
        }
        t.textContent = "";
    }

    // zoom
    function zoom_reset(e) {
        if (e.attributes != undefined) {
            orig_load(e, "x");
            orig_load(e, "width");
        }
        if (e.childNodes == undefined) return;
        for(var i=0, c=e.childNodes; i<c.length; i++) {
            zoom_reset(c[i]);
        }
    }
    function zoom_child(e, x, ratio) {
        if (e.attributes != undefined) {
            if (e.attributes["x"] != undefined) {
                orig_save(e, "x");
                e.attributes["x"].value = (parseFloat(e.attributes["x"].value) - x - $xpad) * ratio + $xpad;
                if(e.tagName == "text") e.attributes["x"].value = find_child(e.parentNode, "rect", "x") + 3;
            }
            if (e.attributes["width"] != undefined) {
                orig_save(e, "width");
                e.attributes["width"].value = parseFloat(e.attributes["width"].value) * ratio;
            }
        }

        if (e.childNodes == undefined) return;
        for(var i=0, c=e.childNodes; i<c.length; i++) {
            zoom_child(c[i], x-$xpad, ratio);
        }
    }
    function zoom_parent(e) {
        if (e.attributes) {
            if (e.attributes["x"] != undefined) {
                orig_save(e, "x");
                e.attributes["x"].value = $xpad;
            }
            if (e.attributes["width"] != undefined) {
                orig_save(e, "width");
                e.attributes["width"].value = parseInt(globalscale*svg.width.baseVal.value) - ($xpad*2);
            }
        }
        if (e.childNodes == undefined) return;
        for(var i=0, c=e.childNodes; i<c.length; i++) {
            zoom_parent(c[i]);
        }
    }
    function zoom(node) {
        svg = document.getElementsByTagName("svg")[0];
        globalscale = svg.viewBox.baseVal.width/svg.width.baseVal.value;
        var attr = find_child(node, "rect").attributes;
        var width = parseFloat(attr["width"].value);
        var xmin = parseFloat(attr["x"].value);
        var xmax = parseFloat(xmin + width);
        var ymin = parseFloat(attr["y"].value);
        var ratio = (globalscale*svg.width.baseVal.value - 2*$xpad) / width;

        // XXX: Workaround for JavaScript float issues (fix me)
        var fudge = 0.0001;

        var unzoombtn = document.getElementById("unzoom");
        unzoombtn.style["opacity"] = "1.0";

        var el = document.getElementsByTagName("g");
        for(var i=0;i<el.length;i++){
            var e = el[i];
            var a = find_child(e, "rect").attributes;
            var ex = parseFloat(a["x"].value);
            var ew = parseFloat(a["width"].value);
            // Is it an ancestor
            if ($inverted == 0) {
                var upstack = parseFloat(a["y"].value) > ymin;
            } else {
                var upstack = parseFloat(a["y"].value) < ymin;
            }
            if (upstack) {
                // Direct ancestor
                if (ex <= xmin && (ex+ew+fudge) >= xmax) {
                    e.style["opacity"] = "0.5";
                    zoom_parent(e);
                    e.onclick = function(e){unzoom(); zoom(this);};
                    update_text(e);
                }
                // not in current path
                else
                    e.style["display"] = "none";
            }
            // Children maybe
            else {
                // no common path
                if (ex < xmin || ex + fudge >= xmax) {
                    e.style["display"] = "none";
                }
                else {
                    zoom_child(e, xmin, ratio);
                    e.onclick = function(e){zoom(this);};
                    update_text(e);
                }
            }
        }
    }
    function unzoom() {
        var unzoombtn = document.getElementById("unzoom");
        unzoombtn.style["opacity"] = "0.0";

        var el = document.getElementsByTagName("g");
        for(i=0;i<el.length;i++) {
            el[i].style["display"] = "block";
            el[i].style["opacity"] = "1";
            zoom_reset(el[i]);
            update_text(el[i]);
        }
    }

    // search
    function reset_search() {
        var el = document.getElementsByTagName("rect");
        for (var i=0; i < el.length; i++) {
            orig_load(el[i], "fill")
        }
    }
    function search_prompt() {
        if (!searching) {
            var term = prompt("Enter a search term (regexp " +
                "allowed, eg: ^ext4_)", "");
            if (term != null) {
                search(term)
            }
        } else {
            reset_search();
            searching = 0;
            searchbtn.style["opacity"] = "0.1";
            searchbtn.firstChild.nodeValue = "Search"
            matchedtxt.style["opacity"] = "0.0";
            matchedtxt.firstChild.nodeValue = ""
        }
    }
    function search(term) {
        var re = new RegExp(term);
        var el = document.getElementsByTagName("g");
        var matches = new Object();
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

                // remember matches
                if (matches[x] == undefined) {
                    matches[x] = w;
                } else {
                    if (w > matches[x]) {
                        // overwrite with parent
                        matches[x] = w;
                    }
                }
                searching = 1;
            }
        }
        if (!searching)
            return;

        searchbtn.style["opacity"] = "1.0";
        searchbtn.firstChild.nodeValue = "Reset Search"

        // calculate percent matched, excluding vertical overlap
        var count = 0;
        var lastx = -1;
        var lastw = 0;
        var keys = Array();
        for (k in matches) {
            if (matches.hasOwnProperty(k))
                keys.push(k);
        }
        // sort the matched frames by their x location
        // ascending, then width descending
        keys.sort(function(a, b){
                return a - b;
            if (a < b || a > b)
                return a - b;
            return matches[b] - matches[a];
        });
        // Step through frames saving only the biggest bottom-up frames
        // thanks to the sort order. This relies on the tree property
        // where children are always smaller than their parents.
        for (var k in keys) {
            var x = parseFloat(keys[k]);
            var w = matches[keys[k]];
            if (x >= lastx + lastw) {
                count += w;
                lastx = x;
                lastw = w;
            }
        }
        // display matched percent
        matchedtxt.style["opacity"] = "1.0";
        pct = 100 * count / maxwidth;
        if (pct == 100)
            pct = "100"
        else
            pct = pct.toFixed(1)
        matchedtxt.firstChild.nodeValue = "Matched: " + pct + "%";
    }
    function searchover(e) {
        searchbtn.style["opacity"] = "1.0";
    }
    function searchout(e) {
        if (searching) {
            searchbtn.style["opacity"] = "1.0";
        } else {
            searchbtn.style["opacity"] = "0.1";
        }
    }
]]>
</script>""")
    return svg_scripts.substitute(values)


class Attributes:

    def __init__(self, info):
        self.attributes = {'class': "\"func_g\"",
                           'onmouseover': "\"s(this)\"",
                           'onmouseout': "\"c()\"",
                           'onclick': "\"zoom(this)\"",
                           'title': info}


class Node:

    def __init__(self, start_time, start_time_2):
        self.start_time = start_time
        self.start_time_2 = start_time_2
        self.exclusive_time = 0
        self.exclusive_time_2 = 0

    def increment_exclusive_time(self, exclusive_time, exclusive_time_2):
        self.exclusive_time += exclusive_time
        self.exclusive_time_2 += exclusive_time_2


class SVGPackage:

    def __init__(self):
        self.svg = []

    def header(self, width, height):
        values = {'width': width, 'height': height}
        svg_header = string.Template("""<?xml version="1.0" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg version="1.1" width="100%" height="100%" onload="init()" onresize="resize()" viewBox="0 0 $width $height" 
xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<!-- Flame graph stack visualization. See https://github.com/brendangregg/FlameGraph for latest version, 
and http://www.brendangregg.com/flamegraphs.html for examples. -->""")
        self.svg.append(svg_header.substitute(values) + "\n")

    def include(self, content):
        self.svg.append(content + "\n")

    @staticmethod
    def allocate_color(r, g, b):
        return "rgb({},{},{})".format(r, g, b)

    def group_start(self, attr):
        g_attributes = "<g class={} onmouseover={} onmouseout={} onclick={}>\n".format(attr.attributes["class"],
                                                                                       attr.attributes["onmouseover"],
                                                                                       attr.attributes["onmouseout"],
                                                                                       attr.attributes["onclick"])
        self.svg.append(g_attributes)
        self.svg.append("<title>{}</title>".format(attr.attributes["title"]))

    def group_end(self):
        self.svg.append("</g>\n")

    def filled_rectangle(self, x1, y1, x2, y2, fill, extra=""):
        x1 = '{:.1f}'.format(x1)
        x2 = '{:.1f}'.format(x2)
        w = '{:.1f}'.format(float(x2) - float(x1))
        h = '{:.1f}'.format(float(y2) - float(y1))
        values = {'x1': x1, 'y1': y1, 'w': w, 'h': h, 'fill': fill, 'extra': extra}
        rectangle = string.Template("""<rect x="$x1" y="$y1" width="$w" height="$h" fill="$fill" $extra/>\n""")
        self.svg.append(rectangle.substitute(values))

    def string_ttf(self, color, font, size, x, y, str_val, loc="left", extra=""):
        x = '{:.2f}'.format(x)
        values = {'loc': loc, 'x': x, 'y': y, 'size': size, 'font': font, 'color': color,
                  'str': str_val, 'extra': extra}
        string_ttf = string.Template(
            """<text text-anchor="$loc" x="$x" y="$y" font-size="$size" font-family="$font" 
            fill="$color" $extra >$str</text>\n""")
        self.svg.append(string_ttf.substitute(values))

    def get_svg(self):
        self.svg.append("</svg>\n")
        return "".join(self.svg)


class ColorHandler:

    def __init__(self):
        self.palette_map = {}

    def color(self, color_type, name):
        v1 = self.namehash(name)
        if color_type:
            if color_type == "aqua":
                r = 50 + int(60 * v1)
                g = 165 + int(55 * v1)
                b = 165 + int(55 * v1)
                return "rgb({},{},{})".format(str(r), str(g), str(b))

    @staticmethod
    def color_scale(value, max_value):
        r = 255
        g = 255
        b = 255
        if value > 0:
            g = int(220 * (max_value - value) / max_value)
            b = g
        elif value < 0:
            r = int(220 * (max_value + value) / max_value)
            g = r
        return "rgb({},{},{})".format(str(r), str(g), str(b))

    @staticmethod
    def color_log_scale(value, mean, max_value):
        r = 255
        g = 255
        b = 255
        if value > 0.000001:
            logmax = math.log(max_value)
            logmean = math.log(mean)
            logvalue = math.log(value)
            if value > mean:
                g = int(255 * ((logmax - logmean - (logvalue - logmean)) / (logmax - logmean)))
                b = g
            elif value < mean:
                r = int(255 * ((logmax - logmean + (logvalue - logmean)) / (logmax - logmean)))
                b = r
        return "rgb({},{},{})".format(str(r), str(g), str(b))

    def read_palette(self, palette_file):
        if os.path.isfile(palette_file):
            fin = open(palette_file, 'r')
            for line in fin:
                colour_map = line.strip().split("->")
                self.palette_map[colour_map[0]] = colour_map[1]
            fin.close()

    def color_map(self, color_type, func):
        if func in self.palette_map:
            return self.palette_map[func]
        else:
            self.palette_map[func] = self.color(color_type, func)
            return self.palette_map[func]

    @staticmethod
    def namehash(name):
        vector = 0
        weight = 1
        max_value = 1
        mod = 10
        name = re.sub(r'.(.*?)`/', '', name)
        for c in list(name):
            i = (ord(c)) % mod
            vector += (i / (mod - 1)) * weight
            mod += 1
            max_value += weight
            weight *= 0.7
            if mod > 12:
                break
        return 1 - (vector / max_value)


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
                            'inverted',
                            'bgcolor1',
                            'bgcolor2',
                            'nametype',
                            'searchcolor',
                            'pal_file',
                            'sort_by_time',
                            'sort_by_name',
                            'colors'])


class FlameGraph:
    """FlameGraph object representing raw SVG for flamegraph"""

    def __init__(self, working_dir, in_file, out_file,
                 description="",
                 custom_event_ratio=False,
                 diff=False,
                 exclusive=True,
                 color_map=None,
                 has_color_map=False,
                 imagewidth=1200,
                 frameheight=16,
                 fontsize=12,
                 fontwidth=0.59,
                 fonttype='Verdana',
                 minwidth=0.1,
                 inverted=0,
                 nametype='Function',
                 searchcolor='rgb(230,0,230)',
                 pal_file='palette.map',
                 sort_by_time=True,
                 sort_by_name=False,
                 colors='aqua',
                 unit="samples"):
        self.working_dir = working_dir
        self.in_file = self.working_dir + os.sep + in_file
        self.out_file = self.working_dir + os.sep + out_file
        self.description = description
        self.custom_event_ratio = custom_event_ratio
        self.diff = diff
        self.exclusive = exclusive
        self.has_color_map = has_color_map
        self.color_handler = ColorHandler()
        if color_map:
            self.color_handler.palette_map = color_map
        self.data_order = []
        self.data = []
        self.other = None
        self.unit = unit
        self.read_data()
        self.sorted_data = []
        self.ignored = 0
        self.processed = 0
        self.max_delta = -sys.float_info.max
        self.upper_delta = -sys.float_info.max
        self.lower_delta = sys.float_info.max
        self.mean_delta = 0.0
        self.mean_samples1 = 0.0
        self.mean_samples2 = 0.0
        self.inclusive_time = 0
        self.exclusive_time = 0
        self.inclusive_time_2 = 0
        self.exclusive_time_2 = 0
        self.depthmax = 0
        self.timemax = 0
        self.tmp = {}
        self.nodes = {}
        self.last = []
        self.image_settings = \
            self.set_image_setings(fontsize, imagewidth, frameheight, fontwidth, fonttype, minwidth, inverted,
                                   nametype, searchcolor, pal_file, sort_by_time, sort_by_name, colors)
        if self.image_settings.sort_by_time:
            self.sort = self.initialise_sort_by_time()
        self.im = SVGPackage()
        self.svg_scripts = self.set_svg_scripts()
        self.process_stacks()

    def set_image_setings(self, fontsize, imagewidth, frameheight, fontwidth, fonttype, minwidth, inverted,
                          nametype, searchcolor, pal_file, sort_by_time, sort_by_name, colors):
        if self.diff or self.custom_event_ratio:
            bgcolor1 = '#eeeeee'
            bgcolor2 = '#eeeeb0'
        else:
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
                             inverted=inverted,
                             bgcolor1=bgcolor1,
                             bgcolor2=bgcolor2,
                             nametype=nametype,
                             searchcolor=searchcolor,
                             pal_file=pal_file,
                             sort_by_time=sort_by_time,
                             sort_by_name=sort_by_name,
                             colors=colors)

    def set_svg_scripts(self):
        xpad = self.image_settings.xpad
        bgcolor1 = self.image_settings.bgcolor1
        bgcolor2 = self.image_settings.bgcolor2
        nametype = self.image_settings.nametype
        fontsize = self.image_settings.fontsize
        fontwidth = self.image_settings.fontwidth
        inverted = self.image_settings.inverted
        searchcolor = self.image_settings.searchcolor
        return get_svg_scripts(xpad, bgcolor1, bgcolor2, nametype, fontsize, fontwidth, inverted, searchcolor)

    def read_data(self):
        fin = open(self.in_file, 'r')
        for line in fin:
            self.data.append(line)
        fin.close()

    def process_stacks(self):
        stack_regex = re.compile(r"^(.*)\s+?(\d+(?:\.\d*)?)$")
        if self.image_settings.sort_by_time:
            self.sorted_data = sorted(self.data, key=cmp_to_key(self.sort))
        elif self.image_settings.sort_by_name:
            self.sorted_data = sorted(self.data, reverse=False)
        else:
            self.sorted_data = self.data
        for line in self.sorted_data:
            match = re.search(stack_regex, line)
            stack = match.group(1)
            samples = match.group(2)
            if stack == "" or samples == "":
                self.ignored += 1
                continue
            samples2 = None
            delta = None
            match = re.search(stack_regex, stack)
            if match:
                samples2 = samples
                stack = match.group(1)
                samples = match.group(2)
            self.mean_samples1 += float(samples)
            if samples2:
              #  if samples2 == "0":
              #      continue
                if self.diff:
                    delta = float(samples2) - float(samples)
                elif self.custom_event_ratio:
                    if float(samples2) > 0.0:
                        delta = float(samples) / float(samples2)
                    else:
                        delta = 0.0
                if abs(delta) > self.max_delta:
                    self.max_delta = abs(delta)
                if delta < self.lower_delta:
                    self.lower_delta = delta
                if delta > self.upper_delta:
                    self.upper_delta = delta
                self.mean_samples2 += float(samples2)
            stack = stack.strip("<>/")
            self.exclusive_time = int(samples)
            if samples2:
                self.exclusive_time_2 = int(samples2)

            self.last = self.flow(self.last, [""] + stack.split(";"), \
                self.inclusive_time, self.exclusive_time, self.inclusive_time_2, self.exclusive_time_2)

            self.inclusive_time += int(samples)
            if samples2:
                self.inclusive_time_2 += int(samples2)
            self.processed += 1
        if self.processed > 0:
            self.mean_samples1 /= float(self.processed)
            if self.mean_samples2 > 0.0:
                self.mean_samples2 /= float(self.processed)
                self.mean_delta = self.mean_samples1 / self.mean_samples2
            self.flow(self.last, [], \
                self.inclusive_time, self.exclusive_time, self.inclusive_time_2, self.exclusive_time_2)
            self.timemax = self.inclusive_time
            self.timemax_2 = self.inclusive_time_2
            self.other = Node(self.timemax, self.timemax_2)
            if self.timemax > 0:
                self.make_svg()
            else:
                self.make_error_svg()
        else:
            self.make_error_svg()

    def flow(self, last, this, inc, exc, inc2, exc2):
        len_a = len(last) - 1
        len_b = len(this) - 1
        group = this[1] if len_b > 0 else ""
        len_same = 0
        for i in range(0, len_a + 1):
            if i > len_b:
                len_same = i
                break
            if last[i] != this[i]:
                len_same = i
                break
            len_same = i + 1
        for i in range(len_a, len_same-1, -1):
            k = last[i] + ";" + str(i)
            node_id = k + ";" + str(inc) + ";" + str(inc2)
            self.nodes[node_id] = \
                Node(self.tmp[k].start_time, self.tmp[k].start_time_2)
            self.nodes[node_id].increment_exclusive_time( \
                self.tmp[k].exclusive_time, self.tmp[k].exclusive_time_2)
            self.nodes[node_id].group = group
            del self.tmp[k]
        for i in range(len_same, len_b + 1):
            k = this[i] + ";" + str(i)
            self.tmp[k] = Node(inc, inc2)
            if i == len_b:
                self.tmp[k].increment_exclusive_time(exc, exc2)
        return this

    def make_error_svg(self):
        imageheight = self.image_settings.fontsize * 5
        imagewidth = self.image_settings.imagewidth
        fonttype = self.image_settings.fonttype
        fontsize = self.image_settings.fontsize
        self.im.header(imagewidth, imageheight)
        self.im.string_ttf(self.im.allocate_color(0, 0, 0), fonttype, fontsize + 2,
                           int(imagewidth / 2), fontsize*2, "No Data", "middle")
        self.write_flamegraph()

    def make_svg(self):
        self.prune()
        imagewidth = self.image_settings.imagewidth
        frameheight = self.image_settings.frameheight
        fonttype = self.image_settings.fonttype
        fontsize = self.image_settings.fontsize
        fontwidth = self.image_settings.fontwidth
        xpad = self.image_settings.xpad
        ypad1 = self.image_settings.ypad1
        ypad2 = self.image_settings.ypad2
        framepad = self.image_settings.framepad
        imageheight = (self.depthmax * frameheight) + ypad1 + ypad2
        self.im.header(imagewidth, imageheight)
        self.im.include(self.svg_scripts)
        if self.diff or self.custom_event_ratio:
            self.im.filled_rectangle(0, 0, imagewidth, imageheight, 'url(#background)')
        else:
            self.im.filled_rectangle(0, 0, imagewidth, imageheight, 'transparent')
        black = self.im.allocate_color(0, 0, 0)
        vdgrey = self.im.allocate_color(160, 160, 160)
        self.im.string_ttf(black, fonttype, fontsize + 5, int(imagewidth / 2), fontsize * 2, "", "middle")
        self.im.string_ttf(black, fonttype, fontsize, xpad, imageheight - (ypad2 / 2), " ", "",
                           "id=\"details\"")
        self.im.string_ttf(black, fonttype, fontsize, xpad, fontsize * 2, "Reset Zoom", "",
                           "id=\"unzoom\" onclick=\"unzoom()\" style=\"opacity:0.0;cursor:pointer\"")
        self.im.string_ttf(black, fonttype, fontsize, imagewidth - xpad - 100, fontsize * 2, "Search", "",
                           "id=\"search\" onmouseover=\"searchover()\" onmouseout=\"searchout()\" "
                           "onclick=\"search_prompt()\" style=\"opacity:0.1;cursor:pointer\"")
        self.im.string_ttf(black, fonttype, fontsize, imagewidth - xpad - 100, imageheight - (ypad2 / 2), " ", "",
                           "id=\"matched\"")
        if self.has_color_map:
            palette_file = self.working_dir + os.sep + self.image_settings.pal_file
            self.color_handler.read_palette(palette_file)
        imagewidth = self.image_settings.imagewidth
        xpad = self.image_settings.xpad
        widthpertime = float(imagewidth - 2 * xpad) / float(self.timemax)
        if self.custom_event_ratio:
            widthpertime_2 = float(imagewidth - 2 * xpad) / float(self.timemax_2)
        for node_id in self.nodes:  # Draw frames
            [func, depth, end_time, end_time_2] = node_id.split(";")
            node = self.nodes[node_id]
            start_time = node.start_time
            start_time_2 = node.start_time_2
            if func == "" and int(depth) == 0:
                end_time = self.timemax
                end_time_2 = self.timemax_2
            inclusive_time = int(end_time) - int(start_time)
            inclusive_time_txt = "{:,}".format(inclusive_time)
            exclusive_time = node.exclusive_time
            exclusive_time_txt = "{:,}".format(exclusive_time)
            inclusive_time_2 = int(end_time_2) - int(start_time_2)
            inclusive_time_2_txt = "{:,}".format(inclusive_time_2)
            exclusive_time_2 = node.exclusive_time_2
            exclusive_time_2_txt = "{:,}".format(exclusive_time_2)
            if func == "" and int(depth) == 0:
                if self.custom_event_ratio:
                    info = "all ({} samples, 100%)".format(inclusive_time_txt)
                else:
                    info = "all ({} samples, 100%)".format(inclusive_time_2_txt)
            else:
                escaped_func = re.sub("&", "&amp;", func)
                escaped_func = re.sub("<", "&lt;", escaped_func)
                escaped_func = re.sub(">", "&gt;", escaped_func)
                escaped_func = re.sub("\"", "&quot;", escaped_func)
                escaped_func = re.sub(" ", "", escaped_func)
                if self.diff:
                    inc_pct = '{:.4f}'.format(100.0 * inclusive_time_2 / float(self.timemax))
                    exc_pct = '{:.4f}'.format(100.0 * exclusive_time_2 / float(self.timemax))
                    if self.exclusive:
                        delta = float(exclusive_time_2) - float(exclusive_time)
                    else:
                        delta = float(inclusive_time_2) - float(inclusive_time)
                    deltapct = "{:.4f}".format(100.0 * delta / float(self.timemax))
                    info = "{} (Inclusive: {} {}, {}%; Exclusive: {} {}, {}%; Difference: {}%)" \
                        .format(escaped_func, inclusive_time_2_txt, self.unit, inc_pct, exclusive_time_2_txt,
                                self.unit, exc_pct, deltapct)
                elif self.custom_event_ratio:
                    inc_pct = '{:.4f}'.format(100.0 * inclusive_time_2 / float(self.timemax_2))
                    exc_pct = '{:.4f}'.format(100.0 * exclusive_time_2 / float(self.timemax_2))
                    delta = 0.0
                    if self.exclusive:
                        if float(exclusive_time_2) > 0.0:
                            delta = float(exclusive_time) / float(exclusive_time_2)
                    elif float(inclusive_time_2) > 0.0:
                        delta = float(inclusive_time) / float(inclusive_time_2)
                    info = "{} (Inclusive: {} {}, {}%; Exclusive: {} {}, {}%; Ratio: {})" \
                        .format(escaped_func, inclusive_time_2_txt, self.unit, inc_pct, exclusive_time_2_txt,
                                self.unit, exc_pct, format_number(delta))
                else:
                    inc_pct = '{:.4f}'.format(100.0 * inclusive_time / float(self.timemax))
                    exc_pct = '{:.4f}'.format(100.0 * exclusive_time / float(self.timemax))
                    info = "{} (Inclusive: {} {}, {}%; Exclusive: {} {}, {}%)"\
                        .format(escaped_func, inclusive_time_txt, self.unit, inc_pct, exclusive_time_txt,
                                self.unit, exc_pct)
            nameattr = Attributes(info)
            self.im.group_start(nameattr)
            if self.custom_event_ratio:
                x1 = xpad + float(start_time_2) * widthpertime_2
                x2 = xpad + float(end_time_2) * widthpertime_2
            else:
                x1 = xpad + float(start_time) * widthpertime
                x2 = xpad + float(end_time) * widthpertime
            y1 = imageheight - ypad2 - (int(depth) + 1) * frameheight + framepad
            y2 = imageheight - ypad2 - int(depth) * frameheight
            if func == "-":
                color = vdgrey
            if self.diff:
                color = self.color_handler.color_scale(delta, self.max_delta)
            elif self.custom_event_ratio:
                color = self.color_handler.color_log_scale(delta, self.mean_delta, self.upper_delta)
            else:
                color = self.color_handler.color_map(self.image_settings.colors, func)
            self.im.filled_rectangle(x1, y1, x2, y2, color, "rx=\"0\" ry=\"0\" group=\"" + node.group + "\"")
            chars = int((float(x2)-float(x1)) / float(fontsize * fontwidth))
            text = ""
            if chars >= 3:
                text = func[0:min(chars, len(func))]
                if chars < len(func):
                    text = text[:-2] + ".."
                text = re.sub("&", "&amp;", text)
                text = re.sub("<", "&lt;", text)
                text = re.sub(">", "&gt;", text)
            self.im.string_ttf(black, fonttype, fontsize, x1 + 3, 3 + 0.5*(y1 + y2), text, "")
            self.im.group_end()
        self.write_flamegraph()

    def prune(self):
        imagewidth = self.image_settings.imagewidth
        xpad = self.image_settings.xpad
        widthpertime = float(imagewidth - 2 * xpad) / float(self.timemax)
        minwidth_time = float(self.image_settings.minwidth) / float(widthpertime)
        delete_nodes = []
        for node_id in self.nodes:
            [depth, end_time] = node_id.split(";")[1:3]
            start_time = self.nodes[node_id].start_time
            if int(end_time) - int(start_time) < minwidth_time:
                delete_nodes.append(node_id)
                continue
            if int(depth) > self.depthmax:
                self.depthmax = int(depth)
        for node_id in delete_nodes:
            self.other.increment_exclusive_time(self.nodes[node_id].exclusive_time, \
                self.nodes[node_id].exclusive_time)
            del self.nodes[node_id]

    def write_flamegraph(self):
        f = open(self.out_file, 'w')
        f.write(self.im.get_svg())
        f.close()

    def initialise_sort_by_time(self):
        self.store_data_order()

        def sort_stacks_by_time(a, b):  # Order each level in call stacks in the order of first appearance
            s_a, _, secondary = a.rpartition(' ')
            s_b, _, primary = b.rpartition(' ')
            if self.custom_event_ratio or self.diff:
                s_a, _, secondary = s_a.rpartition(' ')
                s_b, _, primary = s_b.rpartition(' ')
            stacks_a = s_a.split(";")
            stacks_b = s_b.split(";")
            len_a = len(stacks_a)
            len_b = len(stacks_b)
            for n in range(0, len_a):
                if n == len_b:
                    return 1
                ca = self.data_order[n][stacks_a[n]]
                cb = self.data_order[n][stacks_b[n]]
                if ca > cb:
                    return 1
                if ca < cb:
                    return -1
            return -1
        return sort_stacks_by_time

    def store_data_order(self):
        for line in self.data:
            r, _, secondary = line.rpartition(' ')
            if self.custom_event_ratio or self.diff:
                r, _, secondary = r.rpartition(' ')
            parts = r.split(";")
            n = 0
            for s in parts:
                if n >= len(self.data_order):
                    self.data_order.append({})
                len_data_order = len(self.data_order[n])
                if s not in self.data_order[n]:
                    self.data_order[n][s] = len_data_order
                n += 1
