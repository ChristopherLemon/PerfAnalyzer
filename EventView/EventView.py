from src.svgGraph import ChartWriter
from flask import render_template, request, jsonify, Blueprint
from src.Utilities import purge, timestamp
from src.StackData import StackData, get_job
import src.GlobalData
from src.FlameGraphUtils import FlameGraph
from src.StackData import write_flamegraph_stacks
from .EventModel import EventModel
from src.SourceCode import generate_source_code_table, generate_empty_table, generate_source_code_info
import re
import os

all_stack_data = {}
event_model = EventModel()
svgchart = ChartWriter()


def reset_event_view():
    global all_stack_data
    global svgchart
    global event_model
    all_stack_data = {}
    svgchart = ChartWriter()
    event_model.reset()


EventView = Blueprint('EventView', __name__, template_folder='templates', static_folder='static')


@EventView.route('/event_view', methods=['GET', 'POST'])
def event_view():
    """Request handler for viewing perf event profiles. A single event will be loaded for every process/thread"""
    global all_stack_data
    global svgchart
    event = str(request.args.get('event'))
    custom_event_ratio = bool(re.match(".* / .*", event))
    event_model.event = event
    event_model.custom_event_ratio = custom_event_ratio
    event_model.layout.results = src.GlobalData.results_files
    # Stacks already loaded - just update
    if event in all_stack_data:
        update_event_model(event)
        all_stack_data[event].read_data(start=event_model.start,
                                        stop=event_model.stop,
                                        text_filter=event_model.text_filter,
                                        selected_ids=event_model.selected_ids,
                                        base_case=event_model.reference_id)
    # Load new stack data into memory and set default parameters
    else:
        all_stack_data[event] = StackData(src.GlobalData.results_files,
                                          src.GlobalData.local_data,
                                          src.GlobalData.loaded_cpu_definition,
                                          data_view="event",
                                          data_id=event,
                                          debug=src.GlobalData.debug,
                                          n_proc=src.GlobalData.n_proc)
        update_event_model(event)
    event_model.process_names = all_stack_data[event].get_all_process_names()
    event_model.jobs = all_stack_data[event].get_all_jobs()
    event_model.system_wide = all_stack_data[event].get_system_wide_mode_enabled()
    # Set reference process
    reference_id = all_stack_data[event].get_base_case_id()
    if reference_id.event_type == "custom_event_ratio":
        event_model.reference_count = float(reference_id.count2) / float(reference_id.count1)
    else:
        event_model.reference_count = reference_id.count1
    # Prepare plots
    purge(src.GlobalData.local_data, ".svg")
    event_model.layout.reference_id = event_model.reference_id
    if custom_event_ratio:
        event_model.layout.event_ratios_chart, event_model.layout.event_ratios_table = \
            get_custom_barchart(event, svgchart)
        event_model.layout.scatter_plot = get_2d_plot(event, svgchart)
    else:
        event_model.layout.event_totals_chart, event_model.layout.event_totals_table = \
            get_barchart(event, event_model.hotspots, event_model.diff, svgchart)
        event_model.layout.event_totals_chart2, event_model.layout.event_totals_table2 = \
            get_barchart_totals(event, event_model.diff, svgchart)
        event_model.layout.scatter_plot = None
    event_model.layout.flamegraph = \
        get_flamegraph(event_model.flamegraph_type, event, custom_event_ratio, event_model.diff)
    event_model.layout.event_min_max_chart, event_model.layout.event_min_max_table = \
        get_min_max_chart(event, event_model.hotspots, svgchart)
    event_model.layout.timechart = get_timechart(event, custom_event_ratio, svgchart)
    event_model.layout.show_source = len(src.GlobalData.hpc_results) > 0
    event_model.layout.source_code_table,  event_model.layout.source_code_info, event_model.layout.source_code_line \
        = get_source_code("", event_model.reference_id)
    # Setup general layout
    ids = all_stack_data[event].get_all_process_ids()
    event_model.layout.diff = not custom_event_ratio
    event_model.layout.title = "Event: " + event
    event_model.layout.footer = "Loaded Results: " + " & ".join(event_model.layout.results)
    return render_template('EventView.html',
                           events=src.GlobalData.loaded_cpu_definition.get_active_events(),
                           trace_jobs=src.GlobalData.trace_jobs,
                           event_group_map=src.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=src.GlobalData.loaded_cpu_definition.get_event_groups(),
                           jobs=src.GlobalData.jobs,
                           processes=src.GlobalData.processes,
                           event_model=event_model,
                           enabled_modes=src.GlobalData.enabled_modes,
                           ids=ids)


@EventView.route('/update_all_charts', methods=['GET', 'POST'])
def update_all_charts():
    global event_model
    event = event_model.event
    custom_event_ratio = event_model.custom_event_ratio
    data = request.get_json()
    if 'text_filter' in data:
        event_model.text_filter = data['text_filter']
    if 'new_ref_id' in data:  # Add reference id if not already in flamegraph_ids
        event_model.reference_id = data['new_ref_id']
        old_ids = all_stack_data[event].get_flamegraph_process_ids()
        ids = []
        add_id = True
        for process_id in old_ids:
            if process_id.label == event_model.reference_id:
                add_id = False
            ids.append(process_id)
        if add_id:
            for process_id in event_model.selected_ids:
                if process_id.label == event_model.reference_id:
                    ids.append(process_id)
        all_stack_data[event].set_flamegraph_process_ids(ids)
    if 'start' in data:
        event_model.start = data['start']
        event_model.stop = data['stop']
    if 'process_ids' in data:
        ids = all_stack_data[event].get_all_process_ids()
        event_model.selected_ids = []
        for process_id in ids:
            if process_id.label in data['process_ids']:
                event_model.selected_ids.append(process_id)
    if 'reference_id' in data:
        event_model.reference_id = data["reference_id"]
    if 'direction' in data:
        if data["direction"] == "next":
            event_model.hotspots += 10
        else:
            if event_model.hotspots > 10:
                event_model.hotspots -= 10
    all_stack_data[event].read_data(start=event_model.start,
                                    stop=event_model.stop,
                                    text_filter=event_model.text_filter,
                                    selected_ids=event_model.selected_ids,
                                    base_case=event_model.reference_id)
    purge(src.GlobalData.local_data, ".svg")
    if custom_event_ratio:
        event_model.layout.event_ratios_chart, event_model.layout.event_ratios_table = \
            get_custom_barchart(event, svgchart)
        event_model.layout.scatter_plot = get_2d_plot(event, svgchart)
    else:
        event_model.layout.event_totals_chart, event_model.layout.event_totals_table = \
            get_barchart(event, event_model.hotspots, event_model.diff, svgchart)
        event_model.layout.event_totals_chart2, event_model.layout.event_totals_table2 = \
            get_barchart_totals(event, event_model.diff, svgchart)
    event_model.layout.event_min_max_chart, event_model.layout.event_min_max_table = \
        get_min_max_chart(event, event_model.hotspots, svgchart)
    event_model.layout.flamegraph = \
        get_flamegraph(event_model.flamegraph_type, event, custom_event_ratio, event_model.diff)
    event_model.layout.timechart = get_timechart(event, custom_event_ratio, svgchart)
    reference_id = all_stack_data[event].get_base_case_id()
    if reference_id.event_type == "custom_event_ratio":
        event_model.reference_count = float(reference_id.count2) / float(reference_id.count1)
    else:
        event_model.reference_count = reference_id.count1
    event_model.layout.reference_count = event_model.reference_count
    event_model.layout.reference_id = event_model.reference_id
    event_model.layout.text_filter = event_model.text_filter
    return jsonify(event_model.layout.to_dict())


@EventView.route('/update_flamegraph_ids', methods=['GET', 'POST'])
def update_flamegraph_ids():
    global event_model
    event = event_model.event
    custom_event_ratio = event_model.custom_event_ratio
    data = request.get_json()
    flamegraph_id = data['flamegraph_id']
    if flamegraph_id == "selected":
        ids = event_model.selected_ids
    elif flamegraph_id == "reference":
        ids = [all_stack_data[event].get_base_case_id()]
    else:  # add/remove id from flamegraph ids
        old_ids = all_stack_data[event].get_flamegraph_process_ids()
        ids = []
        add_id = True
        for process_id in old_ids:
            if process_id.label == flamegraph_id:
                add_id = False
            else:
                ids.append(process_id)
        if add_id:
            for process_id in event_model.selected_ids:
                if process_id.label == flamegraph_id:
                    ids.append(process_id)
    all_stack_data[event].set_flamegraph_process_ids(ids)
    event_model.layout.flamegraph = \
        get_flamegraph(event_model.flamegraph_type, event, custom_event_ratio, event_model.diff)
    if event_model.custom_event_ratio:
        event_model.layout.scatter_plot = get_2d_plot(event, svgchart)
    return jsonify(event_model.layout.to_dict())


@EventView.route('/update_source_code', methods=['GET', 'POST'])
def update_source_code():
    global event_model
    data = request.get_json()
    source_symbol = data["source_symbol"]
    label = data["id"]
    event_model.layout.source_code_table, event_model.layout.source_code_info, event_model.layout.source_code_line = \
        get_source_code(source_symbol, label)
    return jsonify(event_model.layout.to_dict())


@EventView.route('/update_flamegraph_mode', methods=['GET', 'POST'])
def update_flamegraph_mode():
    global event_model
    event = event_model.event
    custom_event_ratio = event_model.custom_event_ratio
    data = request.get_json()
    event_model.flamegraph_mode = data['flamegraph_mode']
    if event_model.flamegraph_mode == "hotspots":
        event_model.diff = False
        event_model.flamegraph_type = "plot_for_event"
    elif event_model.flamegraph_mode == "diff_function_names":
        event_model.diff = True
        event_model.flamegraph_type = "diff_symbols"
    elif event_model.flamegraph_mode == "diff_call_stacks":
        event_model.diff = True
        event_model.flamegraph_type = "diff_stack_traces"
    event_model.layout.event_totals_chart, event_model.layout.event_totals_table = \
        get_barchart(event, event_model.hotspots, event_model.diff, svgchart)
    event_model.layout.event_totals_chart2, event_model.layout.event_totals_table2 = \
        get_barchart_totals(event, event_model.diff, svgchart)
    event_model.layout.flamegraph = \
        get_flamegraph(event_model.flamegraph_type, event, custom_event_ratio, event_model.diff)
    return jsonify(event_model.layout.to_dict())


def update_event_model(event):
    global event_model
    event_model.text_filter = ""
    event_model.selected_ids = all_stack_data[event].get_selected_process_ids()
    event_model.flamegraph_ids = all_stack_data[event].get_flamegraph_process_ids()
    event_model.reference_id = all_stack_data[event].get_base_case_id().label
    event_model.start = all_stack_data[event].get_min_x()
    event_model.stop = all_stack_data[event].get_max_x()


def get_flamegraph(flamegraph_type, event, custom_event_ratio, diff):
    # Setup flamegraph
    write_flamegraph_stacks(all_stack_data[event], flamegraph_type)
    flamegraph_filename = timestamp("flamegraph.svg")
    collapsed_stacks_filename = all_stack_data[event].get_collapsed_stacks_filename()
    color_map = svgchart.get_flamegraph_colour_map()
    if custom_event_ratio or diff:
        FlameGraph(src.GlobalData.local_data,
                   collapsed_stacks_filename,
                   flamegraph_filename,
                   diff=diff,
                   custom_event_ratio=custom_event_ratio)
    else:
        FlameGraph(src.GlobalData.local_data,
                   collapsed_stacks_filename,
                   flamegraph_filename,
                   custom_event_ratio=custom_event_ratio,
                   color_map=color_map)
    svgfile = src.GlobalData.local_data + os.sep + flamegraph_filename
    svgfile = os.path.relpath(svgfile, EventView.template_folder)
    return svgfile


def get_source_code(symbol, label):
    job_id = get_job(label)
    for i in range(len(src.GlobalData.hpc_results)):
        if job_id == src.GlobalData.hpc_results[i].get_job_id():
            process_id = all_stack_data[event_model.event].get_process_id_from_label(label)
            source_code_table, source_code_line = \
                generate_source_code_table(all_stack_data[event_model.event], process_id, symbol,
                                           src.GlobalData.hpc_results[i])
            source_code_info = generate_source_code_info(symbol, src.GlobalData.hpc_results[i])
            return source_code_table, source_code_info, source_code_line
    source_code_table, source_code_info, source_code_line = generate_empty_table()
    return source_code_table, source_code_info, source_code_line


def get_barchart(event, hotspots, diff, svg_chart):
    # Setup Bar Chart
    barchart_filename = timestamp("barchart.svg")
    output_file = src.GlobalData.local_data + os.sep + barchart_filename
    if diff:
        event_totals_chart_title = 'Difference Plot for {}: Reference = {}'.format(event, event_model.reference_id)
        chart = svg_chart.generate_vertical_stacked_bar_chart_diff(all_stack_data[event],
                                                                   title=event_totals_chart_title)
        chart.render_to_file(output_file)
        try:
            event_totals_table = chart.render_table(style=False, transpose=True, total=True)
        except Exception as e:
            event_totals_table = ""
    else:
        event_totals_chart_title = 'Total Event count for {}: Reference = {}'.format(event, event_model.reference_id)
        output_event_type = "original"
        chart = svg_chart.generate_vertical_stacked_bar_chart(all_stack_data[event],
                                                              hotspots,
                                                              title=event_totals_chart_title,
                                                              output_event_type=output_event_type,
                                                              write_colourmap=True)
        chart.render_to_file(output_file)
        try:
            event_totals_table = chart.render_table(style=False, transpose=True, total=True)
        except Exception as e:
            event_totals_table = ""
    svgfile = src.GlobalData.local_data + os.sep + barchart_filename
    svgfile = os.path.relpath(svgfile, EventView.template_folder)
    return svgfile, event_totals_table


def get_barchart_totals(event, diff, svg_chart):
    # Setup Bar Chart
    barchart_filename = timestamp("barchart_totals.svg")
    output_file = src.GlobalData.local_data + os.sep + barchart_filename
    if diff:
        event_totals_chart_title = 'Cumulative Difference Plot for {}: Reference = {}'\
            .format(event, event_model.reference_id)
        chart = svg_chart.generate_bar_chart_total_diff(all_stack_data[event],
                                                        title=event_totals_chart_title)
        chart.render_to_file(output_file)
        try:
            event_totals_table = chart.render_table(style=False, transpose=True, total=True)
        except Exception as e:
            event_totals_table = ""
    else:
        event_totals_chart_title = 'Total Event count for {}: Reference = {}'.format(event, event_model.reference_id)
        output_event_type = "original"
        chart = svg_chart.generate_bar_chart(all_stack_data[event],
                                             title=event_totals_chart_title,
                                             output_event_type=output_event_type)
        chart.render_to_file(output_file)
        try:
            event_totals_table = chart.render_table(style=False, transpose=True, total=True)
        except Exception as e:
            event_totals_table = ""
    svgfile = src.GlobalData.local_data + os.sep + barchart_filename
    svgfile = os.path.relpath(svgfile, EventView.template_folder)
    return svgfile, event_totals_table


def get_custom_barchart(event, svg_chart):
    custom_barchart_filename = timestamp("custom_barchart.svg")
    output_file = src.GlobalData.local_data + os.sep + custom_barchart_filename
    event_totals_chart_title = 'Total Event count for {}: Reference = {}'.format(event, event_model.reference_id)
    output_event_type = "custom_event_ratio"
    chart = svg_chart.generate_bar_chart(all_stack_data[event],
                                         title=event_totals_chart_title,
                                         output_event_type=output_event_type)
    chart.render_to_file(output_file)
    try:
        event_ratios_table = chart.render_table(style=False, transpose=True, total=False)
    except Exception as e:
        event_ratios_table = ""
    svgfile = src.GlobalData.local_data + os.sep + custom_barchart_filename
    svgfile = os.path.relpath(svgfile, EventView.template_folder)
    return svgfile, event_ratios_table


def get_min_max_chart(event, hotspots, svg_chart):
    min_max_chart_filename = timestamp("min_max_chart.svg")
    output_file = src.GlobalData.local_data + os.sep + min_max_chart_filename
    event_min_max_chart_title = 'Hotspots Min/Mean/Max for {}'.format(event)
    chart, chart_table = \
        svg_chart.generate_horizontal_stacked_bar_chart(all_stack_data[event], start=hotspots, 
                                                        title=event_min_max_chart_title)
    chart.render_to_file(output_file)
    try:
        event_min_max_table = chart_table.render_table(style=False, total=True)
    except:
        event_min_max_table = ""
    svgfile = src.GlobalData.local_data + os.sep + min_max_chart_filename
    svgfile = os.path.relpath(svgfile, EventView.template_folder)
    return svgfile, event_min_max_table


def get_2d_plot(event, svg_chart):
    scatter_plot_filename = timestamp("scatter_plot.svg")
    output_file = src.GlobalData.local_data + os.sep + scatter_plot_filename
    event1, div, event2 = event.partition(" / ")
    scatter_plot_title = '{} vs {}'.format(event1, event2)
    chart = svg_chart.generate_scatter_plot(all_stack_data[event],
                                            event1,
                                            event2,
                                            title=scatter_plot_title)
    chart.render_to_file(output_file)
    svgfile = src.GlobalData.local_data + os.sep + scatter_plot_filename
    svgfile = os.path.relpath(svgfile, EventView.template_folder)
    return svgfile


def get_timechart(event, custom_event_ratio, svg_chart):
    # Setup Time Lines
    timechart_filename = timestamp("timechart.svg")
    output_file = src.GlobalData.local_data + os.sep + timechart_filename
    if custom_event_ratio:
        event_time_series_title = '({})'.format(event)
    else:
        event_time_series_title = '({} / second)'.format(event)
    chart = svg_chart.generate_timechart(all_stack_data[event],
                                         event_model.start,
                                         event_model.stop,
                                         title=event_time_series_title)
    chart.render_to_file(output_file)
    svgfile = src.GlobalData.local_data + os.sep + timechart_filename
    svgfile = os.path.relpath(svgfile, EventView.template_folder)
    return svgfile
