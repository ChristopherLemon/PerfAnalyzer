__author__ = 'CLemon'
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

# Scripts to be copied into svg file
def get_svg_scripts(xpad, bgcolor1, bgcolor2, nametype, fontsize, fontwidth, inverted, searchcolor):
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
    function init(evt) {
        details = document.getElementById("details").firstChild;
        searchbtn = document.getElementById("search");
        matchedtxt = document.getElementById("matched");
        svg = document.getElementsByTagName("svg")[0];
        globalscale = svg.viewBox.baseVal.width/svg.width.baseVal.value;
        searching = 0;
    }
    function resize(evt) {
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

    def __init__(self, start_time):
        self.start_time = start_time
        self.exclusive_time = 0
        self.has_delta = False

    def increment_exclusive_time(self, exclusive_time):
        self.exclusive_time += exclusive_time

    def increment_delta(self,d):
        if self.has_delta:
            self.delta += d
        else:
            self.delta = d
        self.has_delta = True

class SVGPackage:

    def __init__(self):
        self.svg = []

    def header(self, width, height):
        values = {'width': width, 'height': height}
        svg_header = string.Template("""<?xml version="1.0" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg version="1.1" width="100%" height="100%" onload="init(evt)" onresize="resize(evt)" viewBox="0 0 $width $height" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<!-- Flame graph stack visualization. See https://github.com/brendangregg/FlameGraph for latest version, and http://www.brendangregg.com/flamegraphs.html for examples. -->""")
        self.svg.append(svg_header.substitute(values) + "\n")

    def include(self, content):
        self.svg.append(content + "\n")

    def colorAllocate(self, r, g, b):
        return "rgb({},{},{})".format(r, g, b)

    def group_start(self, attr):
        g_attributes = "<g class={} onmouseover={} onmouseout={} onclick={}>\n".format(attr.attributes["class"],
                                                                                       attr.attributes["onmouseover"],
                                                                                       attr.attributes["onmouseout"],
                                                                                       attr.attributes["onclick"])
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

    def color_scale(self, value, max):
        r = 255
        g = 255
        b = 255
        if value > 0:
            g = int(210 * (max - value) / max)
            b = g
        elif value < 0:
            r = int(210 * (max + value) / max)
            g = r
        return "rgb({},{},{})".format(str(r), str(g), str(b))

    def color_log_scale(self, value, exc, min, mean, max):
        r = 255
        g = 255
        b = 255
        if exc > 0:
            logmax = math.log(max)
            logmean = math.log(mean)
            logmin = abs(math.log(0.000001))
            if min > 0.000001:
                logmin = abs(math.log(min))
            logvalue = logmin
            if value > 0.000001:
                logvalue = math.log(value)
            if logvalue > logmean:
                g = int(210 * (logmax - logvalue) / (logmax - logmean))
                b = g
            elif logvalue < logmean:
                r = int(210 * (logvalue - logmin) / (logmean - logmin))
                b = r
        return "rgb({},{},{})".format(str(r), str(g), str(b))

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

    def __init__(self, working_dir, in_file, out_file,
                 description="",
                 custom_event_ratio=False,
                 diff=False,
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
        self.depthmax = 0
        self.timemax = 0
        self.tmp = {}
        self.nodes = {}
        self.last = []
        self.image_settings = self.set_image_setings(fontsize, imagewidth, frameheight, fontwidth, fonttype, minwidth, inverted,
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
                self.ignored +=1
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
                if samples2 == "0":
                    continue
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
            stack = stack.strip("<>/()")
            if samples2:
                self.exclusive_time = int(samples2)
            else:
                self.exclusive_time = int(samples)

            self.last = self.flow(self.last, [""] + stack.split(";"), self.inclusive_time, self.exclusive_time, delta)

            if samples2:
                self.inclusive_time += int(samples2)
            else:
                self.inclusive_time += int(samples)
            self.processed += 1
        if self.processed > 0:
            self.mean_samples1 /= float(self.processed)
            if self.mean_samples2 > 0.0:
                self.mean_samples2 /= float(self.processed)
                self.mean_delta = self.mean_samples1 / self.mean_samples2
            self.flow(self.last, [], self.inclusive_time, self.exclusive_time, delta)
            self.timemax = self.inclusive_time
            self.other = Node(self.timemax)
            if self.timemax > 0:
                self.make_svg()
            else:
                self.make_error_svg()
        else:
            self.make_error_svg()

    def flow(self, last, this, inc, exc, d=None):
        len_a = len(last) - 1
        len_b = len(this) - 1
        len_same = 0;
        for i in range(0,len_a + 1):
            if i > len_b:
                len_same = i
                break
            if last[i] != this[i]:
                len_same = i
                break
            len_same = i + 1
        for i in range(len_a, len_same-1, -1):
            k = last[i] + ";" + str(i)
            self.nodes[k + ";" + str(inc)] = Node(self.tmp[k].start_time)
            self.nodes[k + ";" + str(inc)].increment_exclusive_time(self.tmp[k].exclusive_time)
            if self.tmp[k].has_delta:
                self.nodes[k + ";" + str(inc)].increment_delta(self.tmp[k].delta)
            del self.tmp[k]
        for i in range(len_same, len_b + 1):
            k = this[i] + ";" + str(i)
            self.tmp[k] = Node(inc)
            if i == len_b:
                self.tmp[k].increment_exclusive_time(exc)
            if d is not None:
                if i == len_b:
                    self.tmp[k].increment_delta(d)
                else:
                    self.tmp[k].increment_delta(0)
        return this

    def make_error_svg(self):
        imageheight = self.image_settings.fontsize * 5
        imagewidth = self.image_settings.imagewidth
        fonttype =  self.image_settings.fonttype
        fontsize = self.image_settings.fontsize
        self.im.header(imagewidth, imageheight)
        self.im.stringTTF(self.im.colorAllocate(0, 0, 0), fonttype, fontsize + 2,
                     int(imagewidth /2), fontsize*2,
                     "No Data", "middle")
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
        description = self.description
        self.im.header(imagewidth, imageheight)
        self.im.include(self.svg_scripts)
        if self.diff or self.custom_event_ratio:
            self.im.filled_rectangle(0, 0, imagewidth, imageheight, 'url(#background)')
        else:
            self.im.filled_rectangle(0, 0, imagewidth, imageheight, 'transparent')
        black = self.im.colorAllocate(0, 0, 0)
        vdgrey = self.im.colorAllocate(160, 160, 160)
        self.im.stringTTF(black, fonttype, fontsize + 5, int(imagewidth / 2), fontsize * 2, "", "middle")
        self.im.stringTTF(black, fonttype, fontsize, xpad, imageheight - (ypad2 / 2), " ", "",
                          "id=\"details\"")
        self.im.stringTTF(black, fonttype, fontsize, xpad, fontsize * 2, "Reset Zoom", ""
                          , "id=\"unzoom\" onclick=\"unzoom()\" style=\"opacity:0.0;cursor:pointer\"")
        self.im.stringTTF(black, fonttype, fontsize, imagewidth - xpad - 100, fontsize * 2, "Search", "",
                          "id=\"search\" onmouseover=\"searchover()\" onmouseout=\"searchout()\" "
                          "onclick=\"search_prompt()\" style=\"opacity:0.1;cursor:pointer\"")
        self.im.stringTTF(black, fonttype, fontsize, imagewidth - xpad - 100, imageheight - (ypad2 / 2), " ", "",
                          "id=\"matched\"")
        if self.has_color_map:
            palette_file = self.working_dir + os.sep + self.image_settings.pal_file
            self.color_handler.read_palette(palette_file)
        imagewidth = self.image_settings.imagewidth
        xpad = self.image_settings.xpad
        widthpertime = float(imagewidth - 2 * xpad) / float(self.timemax)
        minwidth_time = int(float(self.image_settings.minwidth) / widthpertime)
        for node_id in self.nodes:  # Draw frames
            [func, depth, end_time] = node_id.split(";")
            node = self.nodes[node_id]
            if node.has_delta:
                delta = node.delta
            start_time = node.start_time
            if func == "" and int(depth) == 0:
                end_time = self.timemax
            x1 = xpad + float(start_time) * widthpertime
            x2 = xpad + float(end_time) * widthpertime
            y1 = imageheight - ypad2 - (int(depth) + 1) * frameheight + framepad
            y2 = imageheight - ypad2 - int(depth) * frameheight
            inclusive_time = int(end_time) - int(start_time)
            inclusive_time_txt = "{:,}".format(inclusive_time)
            exclusive_time = node.exclusive_time
            exclusive_time_txt = "{:,}".format(exclusive_time)
            if func == "" and int(depth) == 0:
                info = "all ({} samples, 100%)".format(inclusive_time_txt)
            else:
                inc_pct = '{:.4f}'.format(100.0 * inclusive_time / float(self.timemax))
                exc_pct = '{:.4f}'.format(100.0 * exclusive_time / float(self.timemax))
                escaped_func = re.sub("&", "&amp;", func)
                escaped_func = re.sub("<", "&lt;", escaped_func)
                escaped_func = re.sub(">", "&gt;", escaped_func)
                escaped_func = re.sub("\"", "&quot;", escaped_func)
                escaped_func = re.sub(" ", "", escaped_func)
                if node.has_delta:
                    if self.diff:
                        deltapct = "{:.4f}".format(100.0 * delta / float(self.timemax))
                        info = "{} (Inclusive: {} {}, {}%; Exclusive: {} {}, {}%; Difference: {}%)" \
                            .format(escaped_func, inclusive_time_txt, self.unit, inc_pct, exclusive_time_txt, self.unit, exc_pct, deltapct)
                    else:  # self.custom (ratio)
                        info = "{} (Inclusive: {} {}, {}%; Exclusive: {} {}, {}%; Ratio: {})" \
                            .format(escaped_func, inclusive_time_txt, self.unit, inc_pct, exclusive_time_txt, self.unit, exc_pct, format_number(delta))
                else:
                    info = "{} (Inclusive: {} {}, {}%; Exclusive: {} {}, {}%)"\
                        .format(escaped_func, inclusive_time_txt, self.unit, inc_pct, exclusive_time_txt, self.unit, exc_pct)
            nameattr = Attributes(info)
            self.im.group_start(nameattr)
            if func == "-":
                color = vdgrey
            elif node.has_delta:
                if self.diff:
                    color = self.color_handler.color_scale(delta, self.max_delta)
                else:  # self.custom (ratio)
                    color = self.color_handler.color_log_scale(delta, node.exclusive_time, self.lower_delta,
                                                               self.mean_delta, self.upper_delta)
            else:
                color = self.color_handler.color_map(self.image_settings.colors, func)
            self.im.filled_rectangle(x1, y1, x2, y2, color, "rx=\"2\" ry=\"2\"")
            chars = int((float(x2)-float(x1)) / float(fontsize * fontwidth))
            text = ""
            if chars >= 3:
                text = func[0:min(chars,len(func))]
                if chars < len(func):
                    text = text[:-2] + ".."
                text = re.sub("&", "&amp;", text)
                text = re.sub("<", "&lt;", text)
                text = re.sub(">", "&gt;", text)
            self.im.stringTTF(black, fonttype, fontsize, x1 + 3, 3 + 0.5*(y1 + y2), text, "")
            self.im.group_end(nameattr)
        self.write_flamegraph()

    def prune(self):
        imagewidth = self.image_settings.imagewidth
        xpad = self.image_settings.xpad
        widthpertime = float(imagewidth - 2 * xpad) / float(self.timemax)
        minwidth_time = float(self.image_settings.minwidth) / float(widthpertime)
        delete_nodes = []
        for node_id in self.nodes:
            [func, depth, end_time] = node_id.split(";")
            start_time = self.nodes[node_id].start_time
            if int(end_time) - int(start_time) < minwidth_time:
                delete_nodes.append(node_id)
                continue
            if int(depth) > self.depthmax:
                self.depthmax = int(depth)
        for node_id in delete_nodes:
            self.other.increment_exclusive_time(self.nodes[node_id].exclusive_time)
            if self.nodes[node_id].has_delta:
                self.other.increment_delta(self.nodes[node_id].delta)
            del self.nodes[node_id]

    def write_flamegraph(self):
        f = open(self.out_file, 'w')
        f.write(self.im.get_svg())
        f.close()

    def initialise_sort_by_time(self):
        stack_regex = re.compile(r"^(.*)\s+?(\d+(?:\.\d*)?)$")
        self.store_data_order()
        def sort_stacks_by_time(a, b):  # Order each level in call stacks in the order of first appearance
            s_a = re.search(stack_regex, a).group(1)
            s_b = re.search(stack_regex, b).group(1)
            if self.custom_event_ratio or self.diff:
                s_a = re.search(stack_regex, s_a).group(1)
                s_b = re.search(stack_regex, s_b).group(1)
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
            return -1
        return sort_stacks_by_time

    def store_data_order(self):
        stack_regex = re.compile(r"^(.*)\s+?(\d+(?:\.\d*)?)$")
        for line in self.data:
            r = re.search(stack_regex, line).group(1)
            if self.custom_event_ratio or self.diff:
                r = re.search(stack_regex, r).group(1)
            parts = r.split(";")
            n = 0
            for s in parts:
                if n >= len(self.data_order):
                    self.data_order.append({})
                len_data_order = len(self.data_order[n])
                if s not in self.data_order[n]:
                    self.data_order[n][s] = len_data_order
                n += 1