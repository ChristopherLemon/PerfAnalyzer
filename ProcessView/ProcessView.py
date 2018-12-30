from plotting.svgGraph import ChartWriter
from flask import render_template, request, jsonify, Blueprint
from tools.Utilities import purge, timestamp
from tools.StackData import StackData
import tools.GlobalData
from plotting.FlameGraphUtils import FlameGraph
from tools.StackData import write_flamegraph_stacks, get_job
from .ProcessModel import ProcessModel
from plotting.SourceCode import generate_source_code_table, generate_empty_table
import os

all_stack_data = {}
process_model = ProcessModel()
svgchart = ChartWriter()


def reset_process_view():
    global all_stack_data
    global svgchart
    global process_model
    all_stack_data = {}
    svgchart = ChartWriter()
    process_model.reset()


ProcessView = Blueprint('ProcessView', __name__, template_folder='templates', static_folder='static')


@ProcessView.route('/process_view', methods=['GET', 'POST'])
def process_view():
    """Request handler for viewing perf process profiles. All events/threads will be loaded for a single process"""
    global process_model
    global all_stack_data
    global svgchart
    process = str(request.args.get('process'))
    process_model.process = process
    process_model.layout.results = tools.GlobalData.results_files
    if process in all_stack_data:
        update_process_model(process)
        all_stack_data[process].read_data(start=process_model.start,
                                          stop=process_model.stop,
                                          text_filter=process_model.text_filter,
                                          selected_ids=process_model.selected_ids,
                                          base_case=process_model.reference_id)
    else:
        all_stack_data[process] = StackData(tools.GlobalData.results_files,
                                            tools.GlobalData.local_data,
                                            tools.GlobalData.loaded_cpu_definition,
                                            data_view="process",
                                            data_id=process,
                                            debug=tools.GlobalData.debug,
                                            n_proc=tools.GlobalData.n_proc)
        update_process_model(process)
    process_model.event_names = all_stack_data[process].get_all_event_names()
    process_model.jobs = all_stack_data[process].get_all_jobs()
    process_model.system_wide = all_stack_data[process].get_system_wide_mode_enabled()
# Set reference process
    reference_id = all_stack_data[process].get_base_case_id()
    process_model.reference_event_type = reference_id.event_type
    process_model.reference_id = reference_id.label
    if reference_id.event_type == "custom_event_ratio":
        process_model.reference_count = float(reference_id.count2) / float(reference_id.count1)
    else:
        process_model.reference_count = reference_id.count1
    process_model.num_custom_event_ratios = tools.GlobalData.loaded_cpu_definition.get_num_custom_event_ratios()
# Prepare plots
    purge(tools.GlobalData.local_data, ".svg")
    process_model.layout.reference_id = process_model.reference_id
    process_model.layout.event_totals_chart, process_model.layout.event_totals_table = get_barchart(process, svgchart)
    if process_model.num_custom_event_ratios > 0:
        process_model.layout.event_ratios_chart = get_custom_barchart(process, svgchart)
    process_model.layout.flamegraph = get_flamegraph(process)
    process_model.layout.event_time_series, process_model.layout.event_ratio_time_series = \
        get__timechart(process, svgchart)
    process_model.layout.source_code_table, process_model.layout.source_code_line = get_source_code("")
# Setup general layout
    ids = all_stack_data[process].get_all_process_ids()
    process_model.layout.diff = True
    process_model.layout.title = "Process: " + process
    process_model.layout.footer = "Loaded Results: " + " & ".join(process_model.layout.results)
    return render_template('ProcessView.html',
                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                           event_group_map=tools.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                           jobs=tools.GlobalData.jobs,
                           processes=tools.GlobalData.processes,
                           process_model=process_model,
                           enabled_modes=tools.GlobalData.enabled_modes,
                           ids=ids)


@ProcessView.route('/update_all_charts', methods=['GET', 'POST'])
def update_all_charts():
    global process_model
    global svgchart
    process = process_model.process
    data = request.get_json()
    if 'text_filter' in data:
        process_model.text_filter = data['text_filter']
    if 'new_ref_id' in data:  # Add reference id if not already in flamegraph_ids
        process_model.reference_id = data['new_ref_id']
        old_ids = all_stack_data[process].get_flamegraph_process_ids()
        ids = []
        add_id = True
        for process_id in old_ids:
            if process_id.label == process_model.reference_id:
                add_id = False
                process_model.flamegraph_event_type = process_id.event_type
            ids.append(process_id)
        if add_id:
            for process_id in process_model.selected_ids:
                if process_id.label == process_model.reference_id:
                    ids.append(process_id)
                    process_model.flamegraph_event_type = process_id.event_type
        all_stack_data[process].set_flamegraph_process_ids(ids)
    if 'start' in data:
        process_model.start = data['start']
        process_model.stop = data['stop']
    if 'process_ids' in data:
        ids = all_stack_data[process].get_all_process_ids()
        process_model.selected_ids = []
        for process_id in ids:
            if process_id.label in data['process_ids']:
                process_model.selected_ids.append(process_id)
    if 'reference_id' in data:
        process_model.reference_id = data["reference_id"]
    all_stack_data[process].read_data(start=process_model.start,
                                      stop=process_model.stop,
                                      text_filter=process_model.text_filter,
                                      selected_ids=process_model.selected_ids,
                                      base_case=process_model.reference_id)
    process_model.reference_event_type = all_stack_data[process].get_base_case_id().event_type
    purge(tools.GlobalData.local_data, ".svg")
    process_model.layout.event_totals_chart, process_model.layout.event_totals_table = get_barchart(process, svgchart)
    if process_model.num_custom_event_ratios > 0:
        process_model.layout.event_ratios_chart = get_custom_barchart(process, svgchart)
    process_model.layout.flamegraph = get_flamegraph(process, flamegraph_event_type=process_model.flamegraph_event_type)
    reference_id = all_stack_data[process].get_base_case_id()
    if reference_id.event_type == "custom_event_ratio":
        process_model.reference_count = float(reference_id.count2) / float(reference_id.count1)
    else:
        process_model.reference_count = reference_id.count1
    process_model.layout.event_time_series, process_model.layout.event_ratio_time_series = \
        get__timechart(process, svgchart)
    process_model.layout.reference_count = process_model.reference_count
    process_model.layout.reference_id = process_model.reference_id
    process_model.layout.text_filter = process_model.text_filter
    return jsonify(process_model.layout.to_dict())


@ProcessView.route('/update_flamegraph_ids', methods=['GET', 'POST'])
def update_flamegraph_ids():
    global process_model
    process = process_model.process
    data = request.get_json()
    flamegraph_id = data['flamegraph_id']
    if flamegraph_id == "selected":
        ids = process_model.selected_ids
    elif flamegraph_id == "reference":
        ids = [all_stack_data[process].get_base_case_id()]
    else:  # add/remove id from flamegraph ids
        old_ids = all_stack_data[process].get_flamegraph_process_ids()
        ids = []
        add_id = True
        for process_id in old_ids:
            if process_id.label == flamegraph_id:
                add_id = False
                process_model.flamegraph_event_type = process_id.event_type
            else:
                ids.append(process_id)
        if add_id:
            for process_id in process_model.selected_ids:
                if process_id.label == flamegraph_id:
                    ids.append(process_id)
                    process_model.flamegraph_event_type = process_id.event_type
    all_stack_data[process].set_flamegraph_process_ids(ids)
    process_model.layout.flamegraph = get_flamegraph(process, flamegraph_event_type=process_model.flamegraph_event_type)
    return jsonify(process_model.layout.to_dict())


@ProcessView.route('/update_source_code', methods=['GET', 'POST'])
def update_source_code():
    global process_model
    data = request.get_json()
    source_symbol = data["source_symbol"]
    process_model.layout.source_code_table, process_model.layout.source_code_line = get_source_code(source_symbol)
    return jsonify(process_model.layout.to_dict())


def update_process_model(process):
    global process_model
    process_model.text_filter = ""
    process_model.flamegraph_event_type = "original"
    process_model.selected_ids = all_stack_data[process].get_selected_process_ids()
    process_model.flamegraph_ids = all_stack_data[process].get_flamegraph_process_ids()
    process_model.reference_id = all_stack_data[process].get_base_case_id().label
    process_model.start = all_stack_data[process].get_min_x()
    process_model.stop = all_stack_data[process].get_max_x()


def get_flamegraph(process, flamegraph_event_type="original"):
    # Setup flamegraph
    flamegraph_type = "plot_for_process"
    write_flamegraph_stacks(all_stack_data[process], flamegraph_type, output_event_type=flamegraph_event_type)
    color_map = svgchart.get_flamegraph_colour_map()
    flamegraph_filename = timestamp("flamegraph.svg")
    collapsed_stacks_filename = all_stack_data[process].get_collapsed_stacks_filename()
    if flamegraph_event_type == "custom_event_ratio":
        FlameGraph(tools.GlobalData.local_data,
                   collapsed_stacks_filename,
                   flamegraph_filename,
                   custom_event_ratio=True)
    else:  # original
        FlameGraph(tools.GlobalData.local_data,
                   collapsed_stacks_filename,
                   flamegraph_filename,
                   color_map=color_map,
                   custom_event_ratio=False)
    svgfile = tools.GlobalData.local_data + os.sep + flamegraph_filename
    svgfile = os.path.relpath(svgfile, ProcessView.template_folder)
    return svgfile


def get_source_code(symbol):
    job_id = get_job(process_model.reference_id)
    for i in range(len(tools.GlobalData.hpc_results)):
        if job_id == tools.GlobalData.hpc_results[i].get_job_id():
            source_code_table, source_code_line = \
                generate_source_code_table(all_stack_data[process_model.process],
                                           symbol, tools.GlobalData.hpc_results[i])
            return source_code_table, source_code_line
    source_code_table, source_code_line = generate_empty_table()
    return source_code_table, source_code_line


def get_barchart(process, svg_chart):
    # Setup Bar Charts
    event_totals_chart_title = 'Total Event Counts for {}: Reference = {}'.format(process, process_model.reference_id)
    barchart_filename = timestamp("barchart.svg")
    output_file = tools.GlobalData.local_data + os.sep + barchart_filename
    chart = svg_chart.generate_vertical_stacked_bar_chart(all_stack_data[process],
                                                          title=event_totals_chart_title,
                                                          output_event_type="original",
                                                          write_colourmap=True)
    chart.render_to_file(output_file)
    chart = svg_chart.generate_vertical_stacked_bar_chart(all_stack_data[process],
                                                          title=event_totals_chart_title,
                                                          number_to_rank=30,
                                                          output_event_type="any")
    try:
        event_totals_table = chart.render_table(style=False, transpose=True, total=True)
    except Exception as e:
        event_totals_table = ""
    svgfile = tools.GlobalData.local_data + os.sep + barchart_filename
    svgfile = os.path.relpath(svgfile, ProcessView.template_folder)
    return svgfile, event_totals_table


def get_custom_barchart(process, svg_chart):
    event_ratios_chart_title = 'Average Event Ratios for {}: Reference = {}'.format(process, process_model.reference_id)
    custom_barchart_filename = timestamp("custom_barchart.svg")
    output_file = tools.GlobalData.local_data + os.sep + custom_barchart_filename
    chart = svg_chart.generate_bar_chart(all_stack_data[process],
                                         title=event_ratios_chart_title,
                                         output_event_type="custom_event_ratio")
    chart.render_to_file(output_file)
    svgfile = tools.GlobalData.local_data + os.sep + custom_barchart_filename
    svgfile = os.path.relpath(svgfile, ProcessView.template_folder)
    return svgfile


def get__timechart(process, svg_chart):
    # Setup Time Lines
    event_time_series_filename = timestamp("event_time_series.svg")
    event_ratio_time_series_filename = timestamp("event_ratio_time_series.svg")
    event_time_series_output_file = tools.GlobalData.local_data + os.sep + event_time_series_filename
    event_ratio_time_series_output_file = tools.GlobalData.local_data + os.sep + event_ratio_time_series_filename
    event_time_series_title = '(Event Counts / second) for {}'.format(process)
    event_ratio_time_series_title = 'Event Ratios for {}'.format(process)
    chart = svg_chart.generate_timechart(all_stack_data[process],
                                         process_model.start,
                                         process_model.stop,
                                         title=event_time_series_title,
                                         event_type="original")
    chart.render_to_file(event_time_series_output_file)
    chart = svg_chart.generate_timechart(all_stack_data[process],
                                         process_model.start,
                                         process_model.stop,
                                         title=event_ratio_time_series_title,
                                         event_type="custom_event_ratio")
    chart.render_to_file(event_ratio_time_series_output_file)
    svgfile1 = tools.GlobalData.local_data + os.sep + event_time_series_filename
    svgfile1 = os.path.relpath(svgfile1, ProcessView.template_folder)
    svgfile2 = tools.GlobalData.local_data + os.sep + event_ratio_time_series_filename
    svgfile2 = os.path.relpath(svgfile2, ProcessView.template_folder)
    return svgfile1, svgfile2
