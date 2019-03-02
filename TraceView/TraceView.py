import sys
import os

from flask import render_template, request, jsonify, Blueprint

from src.PlotUtils import ChartWriter
from src.ColourMaps import get_top_ten_colours
from src.Utilities import purge, timestamp
from src.TraceData import TraceData
import src.GlobalData as GlobalData
from src.FlameGraphUtils import FlameGraph
from src.TimeLines import TimeLines
from src.TraceData import write_flamegraph_stacks, get_timeline_data
from TraceView.TraceModel import TraceModel

all_stack_data = {}
trace_model = TraceModel()
svgchart = ChartWriter()


def reset_trace_view():
    global all_stack_data
    global svgchart
    global trace_model
    all_stack_data = {}
    svgchart = ChartWriter()
    trace_model.reset()


TraceView = Blueprint('TraceView', __name__, template_folder='templates', static_folder='static')


@TraceView.route('/trace_view', methods=['GET', 'POST'])
def trace_view():
    """Request handler for viewing perf trace profiles."""
    global all_stack_data
    global svgchart
    job = str(request.args.get('job'))
    trace_model.job = job
    trace_model.start = 0.0
    trace_model.stop = sys.maxsize
    trace_model.layout.results = GlobalData.results_files
    # Stacks already loaded - just update
    if job in all_stack_data:
        update_trace_model(job)
        all_stack_data[job].read_data(start=trace_model.start,
                                      stop=trace_model.stop,
                                      selected_ids=trace_model.selected_ids)
    # Load new stack data into memory and set default parameters
    else:
        all_stack_data[job] = TraceData(GlobalData.results_files,
                                        GlobalData.local_data,
                                        GlobalData.loaded_cpu_definition,
                                        data_id=job,
                                        debug=GlobalData.debug,
                                        n_proc=GlobalData.n_proc)
        update_trace_model(job)
    trace_model.process_names = all_stack_data[job].get_all_process_names()
    trace_model.jobs = all_stack_data[job].get_all_jobs()
    trace_model.system_wide = all_stack_data[job].get_system_wide_mode_enabled()

# Prepare plots
    purge(GlobalData.local_data, ".svg")
    flamegraph_type = "cumulative"
    trace_model.layout.flamegraph = get_flamegraph(flamegraph_type, job, trace_model.start, trace_model.stop)
    trace_model.layout.timelines = get_timelines(job, trace_model.start, trace_model.stop)
# Setup general layout
    ids = all_stack_data[job].get_all_process_ids()
    trace_model.layout.reference_id = ids[0].label
    trace_model.layout.title = "Trace Analysis: " + job
    trace_model.layout.footer = "Loaded Results: " + " & ".join(trace_model.layout.results)
    return render_template('TraceView.html',
                           events=GlobalData.loaded_cpu_definition.get_active_events(),
                           trace_jobs=GlobalData.trace_jobs,
                           event_group_map=GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=GlobalData.loaded_cpu_definition.get_event_groups(),
                           jobs=GlobalData.jobs,
                           processes=GlobalData.processes,
                           trace_model=trace_model,
                           enabled_modes=GlobalData.enabled_modes,
                           ids=ids)


@TraceView.route('/update_flamegraph_mode', methods=['GET', 'POST'])
def update_flamegraph_mode():
    global trace_model
    data = request.get_json()
    job = trace_model.job
    trace_model.flamegraph_type = data['flamegraph_mode']
    trace_model.layout.start = trace_model.start
    trace_model.layout.stop = trace_model.stop
    trace_model.layout.flamegraph = \
        get_flamegraph(trace_model.flamegraph_type, job, trace_model.start, trace_model.stop)
    return jsonify(trace_model.layout.to_dict())


@TraceView.route('/update_flamegraph_ids', methods=['GET', 'POST'])
def update_flamegraph_ids():
    global trace_model
    data = request.get_json()
    job = trace_model.job
    pid = data["pid"]
    tid = data["tid"]
    ids = all_stack_data[job].get_selected_process_ids()
    for process_id in ids:
        if process_id.pid == pid and process_id.tid == tid:
            all_stack_data[job].set_flamegraph_process_ids([process_id])
            trace_model.reference_id = process_id.label
    trace_model.layout.start = trace_model.start
    trace_model.layout.stop = trace_model.stop
    trace_model.layout.reference_id = trace_model.reference_id
    trace_model.layout.flamegraph = \
        get_flamegraph(trace_model.flamegraph_type, job, trace_model.start, trace_model.stop)
    return jsonify(trace_model.layout.to_dict())


@TraceView.route('/reset_timelines', methods=['GET', 'POST'])
def reset_timelines():
    global trace_model
    job = trace_model.job
    trace_model.start = -0.0000001
    trace_model.stop = sys.maxsize
    purge(GlobalData.local_data, ".svg")
    trace_model.layout.start = trace_model.start
    trace_model.layout.stop = trace_model.stop
    trace_model.layout.flamegraph = get_flamegraph(trace_model.flamegraph_type, job, trace_model.start,
                                                   trace_model.stop)
    trace_model.layout.timelines = get_timelines(job, trace_model.start, trace_model.stop)
    return jsonify(trace_model.layout.to_dict())


@TraceView.route('/update_all_charts', methods=['GET', 'POST'])
def update_all_charts():
    global trace_model
    data = request.get_json()
    job = trace_model.job
    update_timelines = False
    if 'process_ids' in data:
        ids = all_stack_data[job].get_all_process_ids()
        trace_model.selected_ids = []
        for process_id in ids:
            if process_id.label in data['process_ids']:
                trace_model.selected_ids.append(process_id)
        if trace_model.reference_id not in data['process_ids']:
            trace_model.reference_id = trace_model.selected_ids[0].label
        update_timelines = True
    if "selection_mode" in data:
        selection_mode = data["selection_mode"]
        trace_model.start = float(data["start"])
        trace_model.stop = float(data["stop"])
        if selection_mode != "add-remove-process":
            update_timelines = True
    all_stack_data[job].read_data(start=trace_model.start,
                                  stop=trace_model.stop,
                                  selected_ids=trace_model.selected_ids)
    trace_model.layout.reference_id = trace_model.reference_id
    trace_model.layout.start = trace_model.start
    trace_model.layout.stop = trace_model.stop
    trace_model.layout.flamegraph = get_flamegraph(trace_model.flamegraph_type, job, trace_model.start,
                                                   trace_model.stop)
    if update_timelines:
        trace_model.layout.timelines = get_timelines(job, trace_model.start, trace_model.stop)
    return jsonify(trace_model.layout.to_dict())


@TraceView.route('/find_function', methods=['GET', 'POST'])
def find_function():
    global trace_model
    data = request.get_json()
    job = trace_model.job
    pid = data["pid"]
    tid = data["tid"]
    function_name = data["function_name"]
    n = int(data["call_num"])
    forwards = (data["direction"] == "next")
    trace_model.layout.function_name, trace_model.start, trace_model.stop = \
        all_stack_data[job].get_next_call(trace_model.start, trace_model.stop, pid, tid, function_name, n, forwards)
    all_stack_data[job].read_data(start=trace_model.start,
                                  stop=trace_model.stop,
                                  selected_ids=trace_model.selected_ids)
    trace_model.flamegraph_type = "trace"
    trace_model.layout.flamegraph = \
        get_flamegraph(trace_model.flamegraph_type, job, trace_model.start, trace_model.stop)
    trace_model.layout.timelines = get_timelines(job, trace_model.start, trace_model.stop)
    trace_model.layout.start = trace_model.start
    trace_model.layout.stop = trace_model.stop
    return jsonify(trace_model.layout.to_dict())


def update_trace_model(job):
    global trace_model
    trace_model.selected_ids = all_stack_data[job].get_selected_process_ids()
    trace_model.flamegraph_ids = all_stack_data[job].get_flamegraph_process_ids()
    trace_model.reference_id = trace_model.selected_ids[0].label
    trace_model.start = -0.0000001
    trace_model.stop = sys.maxsize


def get_flamegraph(flamegraph_type, job, start, stop):
    # Setup flamegraph
    write_flamegraph_stacks(all_stack_data[job], flamegraph_type, start, stop)
    flamegraph_filename = timestamp("flamegraph.svg")
    collapsed_stacks_filename = all_stack_data[job].get_collapsed_stacks_filename()
    if flamegraph_type == "trace":
        augmented = True
        sort_by_time = False
    else:
        augmented = False
        sort_by_time = True
    event_type = all_stack_data[job].get_trace_event_type()
    if event_type == "clock":
        unit = "&#x03BC;s"  # xml unicode: micro-seconds
    else:
        unit = "events"
    hotspots = all_stack_data[job].get_hotspots(augmented=augmented)
    colors = get_top_ten_colours()
    color_map = {h: colors[hotspots[h]] for h in hotspots}
    FlameGraph(GlobalData.local_data,
               collapsed_stacks_filename,
               flamegraph_filename,
               color_map=color_map,
               sort_by_time=sort_by_time,
               unit=unit)
    svgfile = GlobalData.local_data + os.sep + flamegraph_filename
    svgfile = os.path.relpath(svgfile, TraceView.template_folder)
    return svgfile


def get_timelines(job, start, stop):
    all_stack_data[job].generate_timelines(start, stop)
    timelines_data = get_timeline_data(all_stack_data[job])
    intervals = all_stack_data[job].get_num_timeline_intervals()
    event_map = GlobalData.loaded_cpu_definition.get_available_event_map(event_to_raw_event=False)
    timelines_filename = timestamp("timelines.svg")
    hotspots = all_stack_data[job].get_hotspots(augmented=True)
    colors = get_top_ten_colours()
    color_map = {h: colors[hotspots[h]] for h in hotspots}
    TimeLines(GlobalData.local_data,
              timelines_data,
              timelines_filename,
              intervals,
              event_map,
              color_map=color_map)
    svgfile = GlobalData.local_data + os.sep + timelines_filename
    svgfile = os.path.relpath(svgfile, TraceView.template_folder)
    return svgfile
