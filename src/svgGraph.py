import pygal
import sys
from pygal.style import Style
import operator
from collections import OrderedDict
from src.ColourMaps import get_gradient_colours, get_top_ten_colours, get_distinct_colours
from src.Utilities import format_number

custom_style_barchart = Style(
  font_family='googlefont:Roboto',
  background='transparent',
  plot_background='transparent',
  label_font_size=18,
  title_font_size=20,
  legend_font_size=12,
  value_label_font_size=20,
  value_font_size=20,
  tooltip_font_size=16,
  foreground='#18452e',
  foreground_strong='#53A0E8',
  foreground_subtle='#18452e',
  opacity='.85',
  opacity_hover='1.0',
  transition='400ms ease-in',
  colors=get_top_ten_colours())

custom_style_hotspots = Style(
  font_family='googlefont:Roboto',
  background='transparent',
  plot_background='transparent',
  label_font_size=18,
  title_font_size=20,
  legend_font_size=12,
  value_label_font_size=20,
  value_font_size=20,
  tooltip_font_size=16,
  foreground='#18452e',
  foreground_strong='#53A0E8',
  foreground_subtle='#18452e',
  opacity='.85',
  opacity_hover='1.0',
  transition='400ms ease-in',
  colors=get_distinct_colours())

custom_style_timechart = Style(
  font_family='googlefont:Roboto',
  background='transparent',
  plot_background='transparent',
  label_font_size=18,
  title_font_size=20,
  legend_font_size=12,
  value_label_font_size=20,
  value_font_size=20,
  tooltip_font_size=16,
  foreground='#18452e',
  foreground_strong='#53A0E8',
  foreground_subtle='#18452e',
  opacity='.2',
  opacity_hover='.2',
  transition='400ms ease-in',
  colors=get_distinct_colours())

custom_style_scatterplot = Style(
  font_family='googlefont:Roboto',
  background='transparent',
  plot_background='transparent',
  label_font_size=18,
  title_font_size=20,
  legend_font_size=12,
  value_label_font_size=20,
  value_font_size=20,
  tooltip_font_size=16,
  foreground='#18452e',
  foreground_strong='#53A0E8',
  foreground_subtle='#18452e',
  opacity='.2',
  opacity_hover='.3',
  transition='400ms ease-in',
  colors=get_distinct_colours())


class ChartWriter:

    def __init__(self):
        self.max_points = 200
        self.significant = 0.05
        self.hotspot_map = {}

    @staticmethod
    def generate_empty_chart():
        xy_chart = pygal.XY(x_title="", y_title="", style=custom_style_barchart)
        xy_chart.title = 'Perf Data'
        return xy_chart

    def generate_timechart(self, stack_data, user_minx, user_maxx, title="", event_type="all"):
        """Create plot of event count rate as a function of time"""
        xt = 'Time (s)'
        xy_chart = pygal.XY(x_title=xt,
                            style=custom_style_timechart,
                            truncate_label=5,
                            x_label_rotation=25,
                            height=500,
                            value_formatter=lambda val: format_number(val),
                            show_legend=False)
        xy_chart.title = title
        miny = sys.float_info.max
        maxy = -sys.float_info.max
        ids = stack_data.get_selected_process_ids()
        nseries = 0
        for process_id in ids:
            label = process_id.label
            task_id = process_id.task_id
            pid = process_id.pid
            tid = process_id.tid
            chart_type = stack_data.tasks[task_id].event_type
            if pid not in stack_data.X[task_id]:
                continue
            if tid not in stack_data.X[task_id][pid]:
                continue
            if event_type == chart_type or event_type == "all":
                nseries += 1
                x, y = self.restrict_xy(stack_data.X[task_id][pid][tid],
                                        stack_data.Y[task_id][pid][tid],
                                        user_minx,
                                        user_maxx)
                for yval in y:
                    miny = min(miny, yval)
                    maxy = max(maxy, yval)
                xy_chart.add(label, [(x[i], y[i])for i in range(0, len(y))])
        if nseries > 0:
            return xy_chart
        else:
            return self.generate_empty_chart()

    def generate_scatter_plot(self, stack_data, event1, event2, title="", event_type="all"):
        """Create 2-D scatterplot of event 1 vs event 2"""
        yt = event1
        xt = event2
        xy_chart = pygal.XY(x_title=xt,
                            y_title=yt,
                            style=custom_style_scatterplot,
                            truncate_label=5,
                            x_label_rotation=25,
                            height=500,
                            value_formatter=lambda val: format_number(val),
                            show_legend=False)
        xy_chart.title = title
        ids = stack_data.get_flamegraph_process_ids()
        nseries = 0
        maxx = 0.0
        maxy = 0.0
        x = []
        y = []
        nc = len(ids)
        plot_data = {i: [] for i in range(0, nc)}
        labels = []
        i = 0
        nzeros = 0
        for process_id in ids:
            label = process_id.label
            labels.append(label)
            task_id = process_id.task_id
            x_data, y_data = stack_data.get_custom_event_ratio_stack_data(process_id)
            chart_type = stack_data.tasks[task_id].event_type
            if event_type == chart_type or event_type == "all":
                max_count = -sys.float_info.max
                for stack in y_data:
                    max_count = max(max_count, y_data[stack])
                    maxx = max(maxx, x_data[stack])
                for stack in y_data:
                    node = stack.rpartition(";")[2]
                    xi = x_data[stack]
                    yi = y_data[stack]
                    x.append(xi)
                    y.append(yi)
                    if xi > 0.0 and yi > 0.0:
                        nzeros += 1
                    if xi > 0.0 or yi > 0.0 or nzeros == 1:
                        nseries += 1
                        if xi > 0.0:
                            label = node + ", ratio=" + str(format_number(yi / xi))
                        else:
                            label = node + ", ratio=NAN"
                        plot_data[i].append({'value': (xi, yi), 'label': label})
                if nseries > 0:
                    i += 1
        plot_data = self.restrict_scatter_multiple(plot_data,0.0,maxx,0.0,max_count)
        if nseries > 0:
            max_ratio = 0.0
            for i in range(0, len(x)):
                if x[i] > 0.1*maxx:
                    ratio = y[i] / x[i]
                    if ratio > max_ratio:
                        max_ratio = ratio
                        maxy = y[i] * maxx / x[i]
            if max_ratio > 0.0:
                v0 = (0.0, 0.0)
                v1 = (maxx, 0.25*maxy)
                v2 = (maxx, 0.5*maxy)
                v3 = (maxx, 0.75*maxy)
                v4 = (maxx, maxy)
                v5 = (maxx, 0)
                xy_chart.add('Fourth quartile', [v0, v4, v3, v0], show_dots=False, stroke=True, fill=True)
                xy_chart.add('Third quartile', [v0, v3, v2, v0], show_dots=False, stroke=True, fill=True)
                xy_chart.add('Second quartile', [v0, v2, v1, v0], show_dots=False, stroke=True, fill=True)
                xy_chart.add('First quartile', [v0, v1, v5, v0], show_dots=False, stroke=True, fill=True)
            for i in range(0, nc):
                label = labels[i]
                xy_chart.add(label, plot_data[i], stroke=False)
            return xy_chart
        else:
            return self.generate_empty_chart()

    def generate_cluster_plot(self, analysis_data, process_list, raw_event1, raw_event2, centred, yt="", xt="",
                              title="", xlower=None, ylower=None, xupper=None, yupper=None):
        """Create 2-D scatterplot of event1 vs event 2.
        Colours of points are determined from the ratio of event1 / event2"""
        colours = get_top_ten_colours()
        data = analysis_data.get_cluster_data()
        cluster_labels = analysis_data.get_cluster_labels()
        cluster_map = analysis_data.get_cluster_map()
        nc = analysis_data.get_num_clusters()
        plot_data = {i: [] for i in range(-1, nc+1)}
        nseries = 0
        nzeros = 0
        minx = sys.float_info.max
        miny = sys.float_info.max
        maxx = -sys.float_info.max
        maxy = -sys.float_info.max
        all_stack_data = analysis_data.get_stack_data()
        for stack_name in all_stack_data:
            if stack_name not in process_list:
                continue
            stack_data = all_stack_data[stack_name]
            ids = stack_data.get_selected_process_ids()
            for process_id in ids:
                pid = process_id.pid
                tid = process_id.tid
                job = process_id.job
                for stack in data[job][pid][tid]:
                    node = stack.rpartition(";")[2]
                    if node in data[job][pid][tid]:
                        yi = data[job][pid][tid][node][raw_event1]
                        xi = data[job][pid][tid][node][raw_event2]
                        if xlower:
                            if xi < xlower or xi > xupper or yi < ylower or yi > yupper:
                                continue
                        if abs(xi) > 0.0 and abs(yi) > 0.0:
                            nzeros += 1
                        if abs(xi) > 0.0 or abs(yi) > 0.0 or nzeros == 1:
                            nseries += 1
                            minx = min(minx, xi)
                            miny = min(miny, yi)
                            maxx = max(maxx, xi)
                            maxy = max(maxy, yi)
                            if node in cluster_map[job][pid][tid]:
                                ci = cluster_map[job][pid][tid][node]
                                i = cluster_labels[ci]
                                label = "{}-pid:{}-tid:{}: {}".format(job, pid, tid, node)
                                if i < 0:
                                    plot_data[i].append(
                                        {'value': (xi, yi), 'label': label, 'color': 'grey', 'opacity': 0.2})
                                else:
                                    i = i % len(colours)
                                    plot_data[i].append(
                                        {'value': (xi, yi), 'label': label, 'color': colours[i]})
        plot_data = self.restrict_scatter_multiple(plot_data, minx, maxx, miny, maxy)
        if centred:
            xr = max(abs(minx), abs(maxx))
            yr = max(abs(miny), abs(maxy))
            xrange = (-xr, xr)
            yrange = (-yr, yr)
            xy_chart = pygal.XY(xrange=xrange, range=yrange, x_title=xt, y_title=yt,
                                style=custom_style_timechart, truncate_label=5, x_label_rotation=25,
                                height=500, value_formatter=lambda val: format_number(val), show_legend=False)
        else:
            xy_chart = pygal.XY(x_title=xt, y_title=yt, style=custom_style_timechart,
                                truncate_label=5,  x_label_rotation=25, height=500,
                                value_formatter=lambda val: format_number(val), show_legend=False)
        xy_chart.title = title
        for i in range(nc, -2, -1):
            if i < 0:
                label = 'cluster: none'
                xy_chart.add(label, plot_data[i], stroke=False)
            else:
                label = 'cluster: ' + str(i)
                xy_chart.add(label, plot_data[i], stroke=False)
        if nseries > 0:
            return xy_chart
        else:
            return self.generate_empty_chart()

    def generate_hotspot_scatter_plot(self, analysis_data, process_list, reference_process, reference_id,
                                      raw_event1, raw_event2, centred, 
                                      start=1, number_to_rank=11, yt="", xt="", title="", xlower=None,
                                      ylower=None, xupper=None, yupper=None):
        """Create 2-D scatterplot of event1 vs event 2.
        Colours of points are determined by hotspots for reference event"""
        base_case_id = None
        stack_data = analysis_data.all_stack_data[reference_process]
        ids = stack_data.get_all_process_ids()
        for process_id in ids:
            if reference_id == process_id.label:
                base_case_id = process_id
        if not base_case_id:
            return self.generate_empty_chart()
        x_data = stack_data.get_original_event_stack_data(base_case_id)
        x = {}
        for stack in x_data:
            node = stack.rpartition(";")[2]
            if node not in x:
                x[node] = 0.0
            x[node] += x_data[stack]
        sorted_vals = sorted(x.items(), key=operator.itemgetter(1), reverse=True)
        colours = get_top_ten_colours()
        default_color = colours[-1]
        hotspot_colour_map = {}
        start_index = min(start - 1, len(sorted_vals))
        end_index = min(start - 1 + number_to_rank, len(sorted_vals))
        n = 0
        for v in sorted_vals[start_index:end_index]:
            node = v[0]
            hotspot_colour_map[node] = colours[n]
            n += 1
        data = analysis_data.get_cluster_data()
        plot_data = {i: [] for i in range(0, len(colours))}
        nseries = 0
        nzeros = 0
        minx = sys.float_info.max
        miny = sys.float_info.max
        maxx = -sys.float_info.max
        maxy = -sys.float_info.max
        all_stack_data = analysis_data.get_stack_data()
        for stack_name in all_stack_data:
            if stack_name not in process_list:
                continue
            stack_data = all_stack_data[stack_name]
            ids = stack_data.get_selected_process_ids()
            for process_id in ids:
                pid = process_id.pid
                tid = process_id.tid
                job = process_id.job
                for stack in data[job][pid][tid]:
                    node = stack.rpartition(";")[2]
                    if node in data[job][pid][tid]:
                        yi = data[job][pid][tid][node][raw_event1]
                        xi = data[job][pid][tid][node][raw_event2]
                        if xlower:
                            if xi < xlower or xi > xupper or yi < ylower or yi > yupper:
                                continue
                        if abs(xi) > 0.0 and abs(yi) > 0.0:
                            nzeros += 1
                        if abs(xi) > 0.0 or abs(yi) > 0.0 or nzeros == 1:
                            nseries += 1
                            minx = min(minx, xi)
                            miny = min(miny, yi)
                            maxx = max(maxx, xi)
                            maxy = max(maxy, yi)
                            label = "{}-pid:{}-tid:{}: {}".format(job, pid, tid, node)
                            if node in hotspot_colour_map:
                                colour = hotspot_colour_map[node]
                                i = colours.index(colour) + 1
                                plot_data[i].append({'value': (xi, yi), 'label': label, 'color': colour})
                            else:
                                plot_data[0].append({'value': (xi, yi), 'label': label, 'color': default_color,
                                                     'opacity': 0.2})

        if len(plot_data[0]) > 0:
            nmax = 20 * self.max_points
            plot_data[0] = self.restrict_scatter(plot_data[0], minx, maxx, miny, maxy, nmax)
        if centred:
            xr = max(abs(minx), abs(maxx))
            yr = max(abs(miny), abs(maxy))
            xrange = (-xr, xr)
            yrange = (-yr, yr)
            xy_chart = pygal.XY(xrange=xrange, range=yrange, x_title=xt, y_title=yt, style=custom_style_timechart,
                                truncate_label=5,
                                x_label_rotation=25, height=500, value_formatter=lambda val: format_number(val),
                                show_legend=False)
        else:
            xy_chart = pygal.XY(x_title=xt, y_title=yt, style=custom_style_timechart,
                                truncate_label=5, x_label_rotation=25, height=500,
                                value_formatter=lambda val: format_number(val), show_legend=False)
        xy_chart.title = title
        for i in range(0, len(plot_data)):
            if i == 0:
                label = 'hotspot: none'
                xy_chart.add(label, plot_data[i], stroke=False)
            else:
                label = 'hotspot: ' + str(i)
                xy_chart.add(label, plot_data[i], stroke=False, dots_size=4)
        if nseries > 0:
            return xy_chart
        else:
            return self.generate_empty_chart()

    @staticmethod
    def generate_horizontal_stacked_bar_chart(stack_data, start=1, number_to_rank=11, title=""):
        """Create horizontal stacked bar chart/table of top hotspots, including min/mean/max accross all processes,
        for each loaded job"""
        chart = pygal.HorizontalStackedBar(style=custom_style_hotspots,
                                           truncate_label=5,
                                           x_label_rotation=25,
                                           height=500,
                                           value_formatter=lambda val: format_number(val),
                                           show_legend=False)
        chart.title = title
        base_case_id = stack_data.get_base_case_id()
        event_type = stack_data.tasks[base_case_id.task_id].event_type
        if event_type == "original":
            x_data = stack_data.get_original_event_stack_data(base_case_id)
            x = {}
            for stack in x_data:
                node = stack.rpartition(";")[2]
                if node not in x:
                    x[node] = 0.0
                x[node] += x_data[stack]
            sorted_vals = sorted(x.items(), key=operator.itemgetter(1), reverse=True)
        else:  # type == "custom"
            x_data, y_data = stack_data.get_custom_event_ratio_stack_data(base_case_id)
            x = {}
            for stack in x_data:
                node = stack.rpartition(";")[2]
                if node not in x:
                    x[node] = 0.0
                x[node] += x_data[stack]
            y = {}
            for stack in y_data:
                node = stack.rpartition(";")[2]
                if node not in y:
                    y[node] = 0.0
                y[node] += y_data[stack]
            ratios = {s: float(y[s]) / float(x[s]) for s in x if float(x[s]) >= 0.1}
            sorted_vals = sorted(ratios.items(), key=operator.itemgetter(1), reverse=True)
        start_index = min(start - 1, len(sorted_vals))
        end_index = min(start - 1 + number_to_rank, len(sorted_vals))
        plot_data = {}
        plot_labels = {}
        n_procs = {}
        ids = stack_data.get_selected_process_ids()
        for process_id in ids:
            label = process_id.label
            task_id = process_id.task_id
            job = process_id.job
            chart_type = stack_data.tasks[task_id].event_type
            if job not in plot_data:
                plot_data[job] = {}
                plot_labels[job] = {}
                n_procs[job] = 1
            else:
                n_procs[job] += 1
            if chart_type == "original":
                x_data = stack_data.get_original_event_stack_data(process_id)
                x = {}
                for stack in x_data:
                    node = stack.rpartition(";")[2]
                    if node not in x:
                        x[node] = 0.0
                    x[node] += x_data[stack]
                vals = x
            else:  # type == "custom"
                x_data, y_data = stack_data.get_custom_event_ratio_stack_data(process_id)
                x = {}
                for stack in x_data:
                    node = stack.rpartition(";")[2]
                    if node not in x:
                        x[node] = 0.0
                    x[node] += x_data[stack]
                y = {}
                for stack in y_data:
                    node = stack.rpartition(";")[2]
                    if node not in y:
                        y[node] = 0.0
                    y[node] += y_data[stack]
                vals = {s: float(y[s]) / float(x[s]) for s in x if float(x[s]) >= 0.1}
            for v in sorted_vals[start_index:end_index]:
                s = v[0]
                if s in vals:
                    y = vals[s]
                    if s not in plot_data[job]:
                        plot_data[job][s] = {"min": y, "mean": y, "max": y}
                        plot_labels[job][s] = {"min": label, "max": label}
                    else:
                        ymin = plot_data[job][s]["min"]
                        ymean = plot_data[job][s]["mean"]
                        ymax = plot_data[job][s]["max"]
                        if y < ymin:
                            plot_data[job][s]["min"] = y
                            plot_labels[job][s]["min"] = label
                        plot_data[job][s]["mean"] = ymean + y
                        if y > ymax:
                            plot_data[job][s]["max"] = y
                            plot_labels[job][s]["max"] = label
                else:
                    if s not in plot_data[job]:
                        plot_data[job][s] = {"min": 0.0, "mean": 0.0, "max": 0.0}
                        plot_labels[job][s] = {"min": label, "max": label}
                    else:
                        plot_data[job][s]["min"] = 0.0
                        plot_labels[job][s]["min"] = label
        data_min = {job: [] for job in plot_data}
        data_mean = {job: [] for job in plot_data}
        data_max = {job: [] for job in plot_data}
        for v in sorted_vals[end_index-1::-1]:
            s = v[0]
            for job in plot_data:
                mean = float(plot_data[job][s]["mean"]/float(n_procs[job]))
                for dummy_job in plot_data:
                    if job == dummy_job:
                        data_max[job].append(
                            {'value': plot_data[job][s]["max"] - mean, 'label': plot_labels[job][s]["max"] + ": " + s})
                        data_mean[job].append(
                            {"value": mean - plot_data[job][s]["min"], 'label': job + ": " + s})
                        data_min[job].append(
                            {'value': plot_data[job][s]["min"], 'label': plot_labels[job][s]["min"] + ": " + s})
                    else:  # insert dummy values to display seperate stacks for each job
                        data_max[job].append({'value': 0.0})
                        data_mean[job].append({"value": 0.0})
                        data_min[job].append({'value': 0.0})
            if s == sorted_vals[start_index][0]:
                break
        for job in plot_data:
            chart.add(job + ": min", data_min[job])
            chart.add(job + ": mean", data_mean[job])
            chart.add(job + ": max", data_max[job])
        data_min = []
        data_mean = []
        data_max = []
        x_labels = []
        chart_table = pygal.HorizontalStackedBar(style=custom_style_hotspots,
                                                 truncate_label=5,
                                                 x_label_rotation=25,
                                                 height=500,
                                                 value_formatter=lambda val: format_number(val),
                                                 show_legend=False)
        for v in sorted_vals[start_index:end_index]:
            s = v[0]
            for job in plot_data:
                x_labels.append(job + ": " + s)
                mean = float(plot_data[job][s]["mean"]/float(n_procs[job]))
                data_max.append({'value': plot_data[job][s]["max"], 'label': plot_labels[job][s]["max"] + ": " + s})
                data_mean.append({"value": mean, 'label': s})
                data_min.append({'value': plot_data[job][s]["min"], 'label': plot_labels[job][s]["min"] + ": " + s})

        chart_table.add("min", data_min)
        chart_table.add("mean", data_mean)
        chart_table.add("max", data_max)
        chart_table.x_labels = x_labels
        return chart, chart_table

    def generate_bar_chart(self, stack_data, title="", output_event_type="any"):
        """Create simple bar chart/table for custom event ratio"""
        xt = 'Process\Thread\Event'
        chart = pygal.Bar(x_title=xt,
                          style=custom_style_barchart,
                          truncate_label=5,
                          x_label_rotation=25,
                          height=500,
                          value_formatter=lambda x: format_number(x),
                          show_legend=False)
        chart.title = title
        ids = stack_data.get_selected_process_ids()
        nseries = 0
        x_labels = []
        data = []
        totals = stack_data.get_totals()
        for process_id in ids:
            label = process_id.label
            task_id = process_id.task_id
            pid = process_id.pid
            tid = process_id.tid
            if len(totals[task_id]) == 0:
                continue
            event_type = stack_data.tasks[task_id].event_type
            if output_event_type == event_type or output_event_type == "any":
                if pid in totals[task_id]:
                    if tid in totals[task_id][pid]:
                        nseries += 1
                        x_labels.append(label)
                        data.append({'value': totals[task_id][pid][tid], 'label': label})
        chart.add("Total Event Count", data)
        chart.x_labels = x_labels
        if nseries > 0:
            return chart
        else:
            return self.generate_empty_chart()

    def generate_bar_chart_multiple_jobs(self, all_stack_data, process_list, title="", output_event_type="any"):
        """Create simple bar chart/table for custom event ratio when there are multiple profiles loaded"""
        xt = 'Process\Thread\Event'
        chart = pygal.Bar(x_title=xt,
                          style=custom_style_barchart,
                          truncate_label=5,
                          x_label_rotation=25,
                          height=500,
                          value_formatter=lambda x: format_number(x),
                          show_legend=False)
        chart.title = title
        nseries = 0
        x_labels = []
        data = []
        label_to_event_map = {}
        events = []
        for stack_name in all_stack_data:
            if stack_name not in process_list:
                continue
            stack_data = all_stack_data[stack_name]
            totals = stack_data.get_totals()
            ids = stack_data.get_selected_process_ids()
            for process_id in ids:
                label = process_id.label
                event = process_id.event_name
                task_id = process_id.task_id
                pid = process_id.pid
                tid = process_id.tid
                event_type = stack_data.tasks[task_id].event_type
                if len(totals[task_id]) == 0:
                    continue
                if output_event_type == event_type or output_event_type == "any":
                    label_to_event_map[label] = event
                    if event not in events:
                        events.append(event)
                    if pid in totals[task_id]:
                        if tid in totals[task_id][pid]:
                            nseries += 1
                            x_labels.append(label)
                            data.append({'value': totals[task_id][pid][tid], 'label': label})
        event_ordered_data = []
        event_ordered_x_labels = []
        for event in events:
            for d in data:
                label = d["label"]
                value = d["value"]
                if event == label_to_event_map[label]:
                    event_ordered_x_labels.append(label)
                    event_ordered_data.append({'value': value, 'label': label})
        chart.add("Total Event Count", event_ordered_data)
        chart.x_labels = event_ordered_x_labels
        if nseries > 0:
            return chart
        else:
            return self.generate_empty_chart()

    def generate_vertical_stacked_bar_chart(self, stack_data, start=1, number_to_rank=11, title="",
                                            output_event_type="any", write_colourmap=False):
        """Create vertical stacked bar chart\table for the functions with the largest contributions
        (according to the reference case) to the total event count."""
        chart = pygal.StackedBar(style=custom_style_barchart,
                                 truncate_label=5,
                                 x_label_rotation=25,
                                 height=500,
                                 show_legend=False,
                                 value_formatter=lambda val: format_number(val),
                                 stack_from_top=True)
        chart.title = title
        ids = stack_data.get_selected_process_ids()
        base_case_id = stack_data.get_base_case_id()
        if base_case_id.event_type == "original":
            x_data = stack_data.get_original_event_stack_data(base_case_id)
            x = {}
            for stack in x_data:
                node = stack.rpartition(";")[2]
                if node not in x:
                    x[node] = 0.0
                x[node] += x_data[stack]
            sorted_vals = sorted(x.items(), key=operator.itemgetter(1), reverse=True)
        else:  # custom event ratio
            x_data, y_data = stack_data.get_custom_event_ratio_stack_data(base_case_id)
            x = {}
            for stack in x_data:
                node = stack.rpartition(";")[2]
                if node not in x:
                    x[node] = 0.0
                x[node] += x_data[stack]
            y = {}
            for stack in y_data:
                node = stack.rpartition(";")[2]
                if node not in y:
                    y[node] = 0.0
                y[node] += y_data[stack]
            ratios = {s: float(y[s]) / float(x[s]) for s in x if float(x[s]) >= 0.1}
            sorted_vals = sorted(ratios.items(), key=operator.itemgetter(1), reverse=True)
        start_index = min(start - 1, len(sorted_vals))
        end_index = min(start - 1 + number_to_rank, len(sorted_vals))
        plot_data = OrderedDict()
        x_labels = []
        n_events = 0
        totals = stack_data.get_totals()
        for process_id in ids:
            label = process_id.label
            task_id = process_id.task_id
            pid = process_id.pid
            tid = process_id.tid
            event_type = stack_data.tasks[task_id].event_type
            if len(totals[task_id]) == 0:
                continue
            if event_type == output_event_type or output_event_type == "any":
                if pid in totals[task_id]:
                    if tid in totals[task_id][pid]:
                        n_events += 1
                        x_labels.append(label)
                        other = totals[task_id][pid][tid]
                        if event_type == "original":
                            x_data = stack_data.get_original_event_stack_data(process_id)
                            x = {}
                            for stack in x_data:
                                node = stack.rpartition(";")[2]
                                if node not in x:
                                    x[node] = 0.0
                                x[node] += x_data[stack]
                            vals = x
                        else:  # custom event ratio
                            x_data, y_data = stack_data.get_custom_event_ratio_stack_data(process_id)
                            x = {}
                            for stack in x_data:
                                node = stack.rpartition(";")[2]
                                if node not in x:
                                    x[node] = 0.0
                                x[node] += x_data[stack]
                            y = {}
                            for stack in y_data:
                                node = stack.rpartition(";")[2]
                                if node not in y:
                                    y[node] = 0.0
                                y[node] += y_data[stack]
                            vals = {s: float(y[s]) / float(x[s]) for s in x if float(x[s]) >= 0.1}
                        for v in sorted_vals[start_index:end_index]:
                            s = v[0]
                            if s in vals:
                                y = vals[s]
                                if s not in plot_data:
                                    plot_data[s] = OrderedDict({label: y})
                                else:
                                    plot_data[s][label] = y
                                other -= y
                            else:
                                if s not in plot_data:
                                    plot_data[s] = OrderedDict({label: 0.0})
                                else:
                                    plot_data[s][label] = 0.0
                        if "other" not in plot_data:
                            plot_data["other"] = OrderedDict({label: other})
                        else:
                            plot_data["other"][label] = other
        if n_events > 0:
            if write_colourmap:
                colours = get_top_ten_colours()
                self.hotspot_map = {"other": colours[0]}
            n = 0
            for v in sorted_vals[start_index:end_index]:
                s = v[0]
                if write_colourmap:
                    self.hotspot_map[s] = colours[n]
                n += 1
                data = []
                for label in plot_data[s]:
                    data.append({'value': plot_data[s][label], 'label': label + ": " + s})
                chart.add(s, data)
            data = []
            for label in plot_data["other"]:
                data.append({'value': plot_data["other"][label], 'label': label + ": other"})
            chart.add("other", data)
            chart.x_labels = x_labels
            return chart
        else:
            return self.generate_empty_chart()

    def generate_vertical_stacked_bar_chart_multiple_jobs(self, all_stack_data, process_list, reference_process,
                                                          reference_id, start=1, number_to_rank=11, title="",
                                                          output_event_type="any", write_colourmap=False):
        """Create vertical stacked bar chart\table for the functions with the largest contributions
        (according to the reference case) to the total event count.
        Works with multiple profiles loaded."""
        chart = pygal.StackedBar(style=custom_style_barchart,
                                 truncate_label=5,
                                 x_label_rotation=25,
                                 height=500,
                                 show_legend=False,
                                 value_formatter=lambda val: format_number(val),
                                 stack_from_top=True)
        chart.title = title
        base_case_id = None
        stack_data = all_stack_data[reference_process]
        ids = stack_data.get_all_process_ids()
        for process_id in ids:
            if reference_id == process_id.label:
                base_case_id = process_id
        if not base_case_id:
            return self.generate_empty_chart()

        if base_case_id.event_type == "original":
            x_data = stack_data.get_original_event_stack_data(base_case_id)
            x = {}
            for stack in x_data:
                node = stack.rpartition(";")[2]
                if node not in x:
                    x[node] = 0.0
                x[node] += x_data[stack]
            sorted_vals = sorted(x.items(), key=operator.itemgetter(1), reverse=True)
        else:  # custom event ratio
            x_data, y_data = stack_data.get_custom_event_ratio_stack_data(base_case_id)
            x = {}
            for stack in x_data:
                node = stack.rpartition(";")[2]
                if node not in x:
                    x[node] = 0.0
                x[node] += x_data[stack]
            y = {}
            for stack in y_data:
                node = stack.rpartition(";")[2]
                if node not in y:
                    y[node] = 0.0
                y[node] += y_data[stack]
            ratios = {s: float(y[s]) / float(x[s]) for s in x if float(x[s]) >= 0.1}
            sorted_vals = sorted(ratios.items(), key=operator.itemgetter(1), reverse=True)
        start_index = min(start - 1, len(sorted_vals))
        end_index = min(start - 1 + number_to_rank, len(sorted_vals))
        plot_data = OrderedDict()
        x_labels = []
        n_events = 0
        label_to_event_map = {}
        events = []
        for stack_name in all_stack_data:
            if stack_name not in process_list:
                continue
            stack_data = all_stack_data[stack_name]
            totals = stack_data.get_totals()
            ids = stack_data.get_selected_process_ids()
            for process_id in ids:
                event = process_id.event_name
                label = process_id.label
                task_id = process_id.task_id
                pid = process_id.pid
                tid = process_id.tid
                event_type = stack_data.tasks[task_id].event_type
                if len(totals[task_id]) == 0:
                    continue
                if event_type == output_event_type or output_event_type == "any":
                    if pid in totals[task_id]:
                        if tid in totals[task_id][pid]:
                            n_events += 1
                            x_labels.append(label)
                            other = totals[task_id][pid][tid]
                            if event_type == "original":
                                x_data = stack_data.get_original_event_stack_data(process_id)
                                x = {}
                                for stack in x_data:
                                    node = stack.rpartition(";")[2]
                                    if node not in x:
                                        x[node] = 0.0
                                    x[node] += x_data[stack]
                                vals = x
                            else:  # custom event ratio
                                x_data, y_data = stack_data.get_custom_event_ratio_stack_data(process_id)
                                x = {}
                                for stack in x_data:
                                    node = stack.rpartition(";")[2]
                                    if node not in x:
                                        x[node] = 0.0
                                    x[node] += x_data[stack]
                                y = {}
                                for stack in y_data:
                                    node = stack.rpartition(";")[2]
                                    if node not in y:
                                        y[node] = 0.0
                                    y[node] += y_data[stack]
                                vals = {s: float(y[s]) / float(x[s]) for s in x if float(x[s]) >= 0.1}
                            if event not in events:
                                events.append(event)
                            label_to_event_map[label] = event
                            for v in sorted_vals[start_index:end_index]:
                                s = v[0]
                                if s in vals:
                                    y = vals[s]
                                    if s not in plot_data:
                                        plot_data[s] = OrderedDict({label: y})
                                    else:
                                        plot_data[s][label] = y
                                    other -= y
                                else:
                                    if s not in plot_data:
                                        plot_data[s] = OrderedDict({label: 0.0})
                                    else:
                                        plot_data[s][label] = 0.0
                            if "other" not in plot_data:
                                plot_data["other"] = OrderedDict({label: other})
                            else:
                                plot_data["other"][label] = other
        if n_events > 0:
            event_ordered_plot_data = OrderedDict()
            event_ordered_x_labels = []
            for s in plot_data:
                event_ordered_plot_data[s] = OrderedDict()
                for event in events:
                    for label in plot_data[s]:
                        if event == label_to_event_map[label]:
                            event_ordered_plot_data[s][label] = plot_data[s][label]
            for event in events:
                for label in plot_data[s]:
                    if event == label_to_event_map[label]:
                        event_ordered_x_labels.append(label)
            if write_colourmap:
                colours = get_top_ten_colours()
                self.hotspot_map = {"other": colours[0]}
            n = 0
            for v in sorted_vals[start_index:end_index]:
                s = v[0]
                if write_colourmap:
                    self.hotspot_map[s] = colours[n]
                n += 1
                data = []
                for label in event_ordered_plot_data[s]:
                    data.append({'value': event_ordered_plot_data[s][label], 'label': label + ": " + s})
                chart.add(s, data)
            data = []
            for label in event_ordered_plot_data["other"]:
                data.append({'value': event_ordered_plot_data["other"][label], 'label': label + ": other"})
            chart.add("other", data)
            chart.x_labels = event_ordered_x_labels
            return chart
        else:
            return self.generate_empty_chart()

    def generate_vertical_stacked_bar_chart_diff(self, stack_data, number_to_rank=10, title=""):
        """Create vertical stacked bar chart\table for the functions with the biggest positive/negative differences
        compared to the reference case"""
        ids = stack_data.get_selected_process_ids()
        base_case_id = stack_data.get_base_case_id()
        base_case_task_id = base_case_id.task_id
        base_case_pid = base_case_id.pid
        base_case_tid = base_case_id.tid
        base_case_other = stack_data.totals[base_case_task_id][base_case_pid][base_case_tid]
        x_data = stack_data.get_original_event_stack_data(base_case_id)
        base_case_x = {}

        def plot_data_sort(xi, max_value):
            # To match data order to order used in pygal:
            # Sort from largest +ve to smallest +ve, then from largest -ve to smallest -ve
            val = 0.0
            for xi_key in xi[1]:
                if xi[1][xi_key] > 0.0:
                    val = max(xi[1][xi_key], val)
                elif xi[1][xi_key] < 0.0:
                    val = - max(abs(xi[1][xi_key]), abs(val))
            if val < 0.0:
                val = - (max_value + val)
            return val

        for stack in x_data:
            node = stack.rpartition(";")[2]
            if node not in base_case_x:
                base_case_x[node] = 0.0
            base_case_x[node] += x_data[stack]
        plot_data = OrderedDict()
        x_labels = []
        n_events = 0
        top_nodes = []
        bottom_nodes = []
        max_total = 0.0
        for process_id in [proc_id for proc_id in ids if proc_id.label != base_case_id.label]:
            x_data = stack_data.get_original_event_stack_data(process_id)
            x = {}
            total = 0.0
            for stack in x_data:
                node = stack.rpartition(";")[2]
                if node not in x:
                    x[node] = 0.0
                x[node] += x_data[stack]
                total += x_data[stack]
            if total > max_total:
                max_total = total
            deltas = OrderedDict()
            for s in x:
                deltas[s] = x[s]
            for s in base_case_x:
                if s in deltas:
                    deltas[s] -= base_case_x[s]
                else:
                    deltas[s] = -base_case_x[s]
            sorted_deltas = sorted(deltas.items(), key=operator.itemgetter(1), reverse=True)
            for v in sorted_deltas[0:number_to_rank]:
                s = v[0]
                if s not in top_nodes:
                    top_nodes.append(s)
            for v in sorted_deltas[len(sorted_deltas) - 1:len(sorted_deltas) - number_to_rank - 1:-1]:
                s = v[0]
                if s not in bottom_nodes:
                    bottom_nodes.append(s)
        totals = stack_data.get_totals()
        for process_id in [proc_id for proc_id in ids if proc_id.label != base_case_id.label]:
            unique_label = process_id.label
            task_id = process_id.task_id
            pid = process_id.pid
            tid = process_id.tid
            if len(totals[task_id]) == 0:
                continue
            if pid in totals[task_id]:
                if tid in totals[task_id][pid]:
                    n_events += 1
                    x_labels.append(unique_label)
                    other = totals[task_id][pid][tid] - base_case_other
                    x_data = stack_data.get_original_event_stack_data(process_id)
                    x = {}
                    for stack in x_data:
                        node = stack.rpartition(";")[2]
                        if node not in x:
                            x[node] = 0.0
                        x[node] += x_data[stack]
                    deltas = OrderedDict()
                    for s in x:
                        deltas[s] = x[s]
                    for s in base_case_x:
                        if s in deltas:
                            deltas[s] -= base_case_x[s]
                        else:
                            deltas[s] = -base_case_x[s]
                    for s in top_nodes:
                        if s + ": positive diff" not in plot_data:
                            plot_data[s + ": positive diff"] = OrderedDict()
                            plot_data[s + ": negative diff"] = OrderedDict()
                        if s in deltas:
                            if deltas[s] >= 0.0:
                                plot_data[s + ": positive diff"][unique_label] = deltas[s]
                                plot_data[s + ": negative diff"][unique_label] = 0.0
                                other -= plot_data[s + ": positive diff"][unique_label]
                            else:
                                plot_data[s + ": positive diff"][unique_label] = 0.0
                                plot_data[s + ": negative diff"][unique_label] = deltas[s]
                                other -= plot_data[s + ": negative diff"][unique_label]
                        else:
                            plot_data[s + ": positive diff"][unique_label] = 0.0
                            plot_data[s + ": negative diff"][unique_label] = 0.0
                    for s in bottom_nodes:
                        if s + ": positive diff" not in plot_data:
                            plot_data[s + ": positive diff"] = OrderedDict()
                            plot_data[s + ": negative diff"] = OrderedDict()
                        if s in deltas:
                            if deltas[s] >= 0.0:
                                plot_data[s + ": positive diff"][unique_label] = deltas[s]
                                plot_data[s + ": negative diff"][unique_label] = 0.0
                                other -= plot_data[s + ": positive diff"][unique_label]
                            else:
                                plot_data[s + ": positive diff"][unique_label] = 0.0
                                plot_data[s + ": negative diff"][unique_label] = deltas[s]
                                other -= plot_data[s + ": negative diff"][unique_label]
                        else:
                            plot_data[s + ": positive diff"][unique_label] = 0.0
                            plot_data[s + ": negative diff"][unique_label] = 0.0
                    if "other" + ": positive diff" not in plot_data:
                        plot_data["other" + ": positive diff"] = OrderedDict()
                        plot_data["other" + ": negative diff"] = OrderedDict()
                    if other >= 0.0:
                        plot_data["other" + ": positive diff"][unique_label] = other
                        plot_data["other" + ": negative diff"][unique_label] = 0.0
                    else:
                        plot_data["other" + ": positive diff"][unique_label] = 0.0
                        plot_data["other" + ": negative diff"][unique_label] = other

                plot_data = OrderedDict(
                    sorted(plot_data.items(), key=lambda xi: plot_data_sort(xi, max_total), reverse=True))
                n_pos = 0
                n_neg = 0
                for s in plot_data:
                    if "positive diff" in s:
                        n_pos += 1
                    elif "negative diff" in s:
                        n_neg += 1

        custom_style_barchart_diff = Style(
            font_family='googlefont:Roboto',
            background='transparent',
            plot_background='transparent',
            label_font_size=18,
            title_font_size=20,
            legend_font_size=12,
            value_label_font_size=20,
            value_font_size=20,
            tooltip_font_size=16,
            foreground='#18452e',
            foreground_strong='#53A0E8',
            foreground_subtle='#18452e',
            opacity='.85',
            opacity_hover='1.0',
            transition='400ms ease-in',
            colors=get_gradient_colours(n_pos, n_neg))

        chart = pygal.StackedBar(style=custom_style_barchart_diff,
                                 truncate_label=5,
                                 x_label_rotation=25,
                                 height=500,
                                 show_legend=False,
                                 value_formatter=lambda val: format_number(val),
                                 stack_from_top=True)
        chart.title = title

        if n_events > 0:
            n = 0
            for s in plot_data:
                n += 1
                data = []
                for label in plot_data[s]:
                    data.append({'value': plot_data[s][label], 'label': label + ": " + s})
                chart.add(s, data)
            chart.x_labels = x_labels
            return chart
        else:
            return self.generate_empty_chart()

    def generate_bar_chart_total_diff(self, stack_data, title=""):
        # Create vertical bar chart\table for the functions with the cumulative differences
        # compared to base case
        chart = pygal.Bar(style=custom_style_barchart,
                          truncate_label=5,
                          x_label_rotation=25,
                          height=500,
                          value_formatter=lambda x: format_number(x),
                          show_legend=False)
        chart.title = title
        ids = stack_data.get_selected_process_ids()
        base_case_id = stack_data.get_base_case_id()
        base_case_task_id = base_case_id.task_id
        base_case_pid = base_case_id.pid
        base_case_tid = base_case_id.tid
        base_case_total = stack_data.totals[base_case_task_id][base_case_pid][base_case_tid]
        x_labels = []
        nseries = 0
        data = []
        totals = stack_data.get_totals()
        for process_id in [proc_id for proc_id in ids if proc_id.label != base_case_id.label]:
            label = process_id.label
            task_id = process_id.task_id
            pid = process_id.pid
            tid = process_id.tid
            if len(totals[task_id]) == 0:
                continue
            if pid in totals[task_id]:
                if tid in totals[task_id][pid]:
                    total_diff = totals[task_id][pid][tid] - base_case_total
                    nseries += 1
                    x_labels.append(label)
                    data.append({'value': total_diff, 'label': label})
        chart.add("Total Diff", data)
        chart.x_labels = x_labels
        if nseries > 0:
            return chart
        else:
            return self.generate_empty_chart()

    def restrict_xy(self, x, y, xmin, xmax):
        """Restrict number of points viewed in timeline - so that resolution increases sensibly when zooming into
        a narrower time interval"""
        xc = []
        yc = []
        for xi, yi in zip(x, y):
            if xi > 0.0:
                if xmin <= xi <= xmax:
                    xc.append(xi)
                    yc.append(yi)
        while len(xc) > self.max_points:
            xw = []
            yw = []
            for i, (xci, yci) in enumerate(zip(xc, yc)):
                if i % 2 == 0:
                    xw.append(xci)
                    yw.append(yci)
            xc = xw
            yc = yw
        return xc, yc

    def restrict_scatter_multiple(self, plot_data, xmin, xmax, ymin, ymax):
        total_points = 0
        for i in plot_data:
            total_points += len(plot_data[i])
        if total_points > 20 * self.max_points:
            nscatter = len(plot_data)
            nmax = 40 * self.max_points / nscatter
            for i in plot_data:
                plot_data[i] = self.restrict_scatter(plot_data[i], xmin, xmax, ymin, ymax, nmax)
        return plot_data

    def restrict_scatter(self,plot_data, xmin, xmax, ymin, ymax, nmax):
        """Restrict number of points viewed in scatter plots"""
        if len(plot_data) > nmax:
            reduced_data = []
            for point in plot_data:
                reduced_data.append(point)
            n = 1
            while len(reduced_data) > nmax:
                xy_grid = {}
                data = []
                x_delta = n * (xmax - xmin) / float(self.max_points)
                y_delta = n * (ymax - ymin) / float(self.max_points)
                for point in plot_data:
                    values = point['value']
                    xi = values[0]
                    yi = values[1]
                    xi_grid = int(xi/x_delta)
                    yi_grid = int(yi/y_delta)
                    grid_id = 'x=' + str(xi_grid) + ":y=" + str(yi_grid)
                    if grid_id not in xy_grid:
                        xy_grid[grid_id] = 1
                        data.append(point)
                reduced_data = data
                n += 1
            return reduced_data
        else:
            return plot_data

    def get_flamegraph_colour_map(self):
        return self.hotspot_map
