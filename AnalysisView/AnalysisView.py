from src.svgGraph import ChartWriter
from flask import render_template, request, jsonify, Blueprint
from src.Utilities import purge, timestamp, replace_operators
from src.StackData import StackData, get_job, get_process, get_pid, get_tid, get_event, make_label
from src.ColourMaps import get_top_ten_colours
from src.SourceCode import generate_source_code_table, generate_empty_table, generate_source_code_info
import src.GlobalData
from src.FlameGraphUtils import FlameGraph
from src.StackData import write_flamegraph_stacks
from src.DataAnalysis import GeneralAnalysis
from src.CustomEvents import event_to_raw_event, raw_event_to_event
from .AnalysisModel import AnalysisModel
from collections import OrderedDict
import re
import os
import sys

all_stack_data = {}
all_analysis_data = {}
analysis_model = AnalysisModel()
svgchart = ChartWriter()


def reset_analysis_view():
    global all_stack_data
    global all_analysis_data
    global svgchart
    all_stack_data = {}
    all_analysis_data = {}
    analysis_model.reset()
    svgchart = ChartWriter()


AnalysisView = Blueprint('AnalysisView', __name__, template_folder='templates', static_folder='static')


@AnalysisView.route('/general_analysis', methods=['GET', 'POST'])
def general_analysis():
    # Request handler for general analysis.
    # of event data (event1 vs event2)
    global all_stack_data
    global all_analysis_data
    analysis_type = "general"
    analysis_model.analysis_type = analysis_type
    analysis_data, cluster_events = get_analysis(analysis_type)
    analysis_model.layout.results = src.GlobalData.results_files
    analysis_model.event1, analysis_model.event2 = initialise_analysis_model_cluster_data(analysis_data)
    analysis_model.base_event = src.GlobalData.loaded_cpu_definition.get_base_event()
    base_event = analysis_model.base_event
    events = src.GlobalData.loaded_cpu_definition.get_active_events()
# Load base event to generate complete list of available processes - for selection of required processes
    if base_event in all_stack_data:
        update_analysis_model_base_event_data(base_event, events)
        all_stack_data[base_event].read_data(start=all_stack_data[base_event].start,
                                             stop=all_stack_data[base_event].stop,
                                             text_filter=analysis_model.text_filter,
                                             selected_ids=analysis_model.base_event_selected_ids)
    else:
        all_stack_data[base_event] = StackData(src.GlobalData.results_files,
                                               src.GlobalData.local_data,
                                               src.GlobalData.loaded_cpu_definition,
                                               data_view="event",
                                               data_id=base_event,
                                               debug=src.GlobalData.debug,
                                               n_proc=src.GlobalData.n_proc)
        update_analysis_model_base_event_data(base_event, events)

# Now load selected events on each of the selected processes
    for process in analysis_model.process_list:
        if process in all_stack_data:
            update_analysis_model_process_data(process)
            all_stack_data[process].read_data(start=all_stack_data[process].start,
                                              stop=all_stack_data[process].stop,
                                              text_filter=analysis_model.text_filter,
                                              selected_ids=analysis_model.selected_ids[process],
                                              base_case=analysis_model.reference_id)
        else:
            all_stack_data[process] = StackData(src.GlobalData.results_files,
                                                src.GlobalData.local_data,
                                                src.GlobalData.loaded_cpu_definition,
                                                data_view="process",
                                                data_id=process,
                                                debug=src.GlobalData.debug,
                                                n_proc=src.GlobalData.n_proc)
            update_analysis_model_process_data(process)
            # Update process ids and reference id
            all_stack_data[process].set_selected_process_ids(analysis_model.selected_ids[process])
            all_stack_data[process].set_base_case("", analysis_model.selected_ids[process])
            ids = [all_stack_data[process].get_base_case_id()]
            all_stack_data[process].set_flamegraph_process_ids(ids)
        analysis_data.add_data(all_stack_data[process], process)
# Setup General plot utility
    colours = get_top_ten_colours(return_hex=False)
    analysis_model.num_custom_event_ratios = src.GlobalData.loaded_cpu_definition.get_num_custom_event_ratios()
    centred = (analysis_model.centred_scatter_plot == "centred")
    append_cluster_labels = (analysis_model.flamegraph_mode == "clusters")
    event1 = analysis_model.event1
    event2 = analysis_model.event2
    log_scale = analysis_model.log_scale
    analysis_model.cluster_labels = \
        run_analysis(analysis_data, event1, event2, centred, append_cluster_labels, log_scale)
# Prepare plots
    purge(src.GlobalData.local_data, ".svg")
    analysis_model.layout.reference_id = analysis_model.reference_id
    analysis_model.layout.scatter_plot = \
        get_hotspot_scatter_plot(analysis_data, event1, event2, svgchart, centred, 
                                 analysis_model.hotspots, log_scale)
    analysis_model.layout.event_totals_chart, analysis_model.layout.event_totals_table = \
        get_barchart(analysis_model.process_list, analysis_model.hotspots, svgchart)
    if analysis_model.num_custom_event_ratios > 0:
        analysis_model.layout.event_ratios_chart = get_custom_barchart(analysis_model.process_list, svgchart)
    analysis_model.layout.flamegraph = \
        get_flamegraph(analysis_data, analysis_model.process_list, analysis_model.flamegraph_mode)
    analysis_model.layout.show_source = len(src.GlobalData.hpc_results) > 0
    analysis_model.layout.source_code_table, analysis_model.layout.source_code_info, \
        analysis_model.layout.source_code_line = get_source_code("", analysis_model.reference_id)
# Setup general layout
    analysis_model.layout.title = "Analysis: General"
    analysis_model.layout.footer = "Loaded Results: " + " & ".join(analysis_model.layout.results)
    ids = all_stack_data[base_event].get_all_process_ids()
    return render_template('AnalysisView.html',
                           events=events,
                           trace_jobs=src.GlobalData.trace_jobs,
                           event_group_map=src.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=src.GlobalData.loaded_cpu_definition.get_event_groups(),
                           jobs=src.GlobalData.jobs,
                           processes=src.GlobalData.processes,
                           analysis_model=analysis_model,
                           enabled_modes=src.GlobalData.enabled_modes,
                           ids=ids,
                           colours=colours)


def initialise_analysis_model_cluster_data(analysis_data):
    events_dict = OrderedDict([(raw_event_to_event(event, src.GlobalData.loaded_cpu_definition), event) for event in
                               analysis_data.get_events()])
    analysis_model.cluster_events = events_dict.keys()
    event1 = list(events_dict.keys())[0]
    event2 = list(events_dict.keys())[1]
    return event1, event2

# base_event_reference_id: id of the selected process for the base event - used to store the reference process
# reference_id: actual reference id for the selected process/event combination


def update_analysis_model_base_event_data(base_event, events):
    analysis_model.process_names = all_stack_data[base_event].get_all_process_names()
    analysis_model.jobs = all_stack_data[base_event].get_all_jobs()
    analysis_model.system_wide = all_stack_data[base_event].get_system_wide_mode_enabled()
    analysis_model.base_event_selected_ids = all_stack_data[base_event].get_biggest_process_ids_for_each_job()
    analysis_model.selected_events = events
    analysis_model.reference_event = base_event
    analysis_model.text_filter = ""
    analysis_model.flamegraph_event_type = "original"
    analysis_model.base_event_reference_id = all_stack_data[base_event].get_base_case_id().label
    analysis_model.reference_job = get_job(analysis_model.base_event_reference_id)
    analysis_model.reference_process = get_process(analysis_model.base_event_reference_id)
    analysis_model.reference_pid = get_pid(analysis_model.base_event_reference_id)
    analysis_model.reference_tid = get_tid(analysis_model.base_event_reference_id)
    analysis_model.process_list = []
    for job in src.GlobalData.processes:
        for process in src.GlobalData.processes[job]:
            for process_id in analysis_model.base_event_selected_ids:
                if job == process_id.job and process == process_id.process_name:
                    analysis_model.process_list.append(job + "_" + process)
                    break


def update_analysis_model_process_data(process):
    analysis_model.selected_ids[process] = []
    ids = all_stack_data[process].get_all_process_ids()
    selected_events = analysis_model.selected_events
    for process_id in ids:
        job = process_id.job
        pid = process_id.pid
        tid = process_id.tid
        event = process_id.event_name
        if job == analysis_model.reference_job and \
                pid == analysis_model.reference_pid and \
                tid == analysis_model.reference_tid and \
                event == analysis_model.reference_event:
            analysis_model.reference_id = process_id.label
            analysis_model.reference_process = process
            analysis_model.reference_event_type = process_id.event_type
            if process_id.event_type == "custom_event_ratio":
                analysis_model.reference_count = float(process_id.count2) / float(process_id.count1)
            else:
                analysis_model.reference_count = process_id.count1
            analysis_model.layout.reference_count = analysis_model.reference_count
    for process_id in ids:
        for selected_id in analysis_model.base_event_selected_ids:
            if process_id.job == selected_id.job and \
                    process_id.pid == selected_id.pid and \
                    process_id.tid == selected_id.tid:
                event = process_id.event_name
                if event in selected_events:
                    analysis_model.selected_ids[process].append(process_id)


@AnalysisView.route('/get_new_chart', methods=['GET', 'POST'])
def get_new_chart():
    # Update chart for custom analysis when the selected events have been changed
    global all_analysis_data
    global svgchart
    global analysis_model
    data = request.get_json()
    analysis_type = analysis_model.analysis_type
    analysis_data = all_analysis_data[analysis_type]
    event1 = data['event1']
    event2 = data['event2']
    analysis_model.event1 = event1
    analysis_model.event2 = event2
    process_list = analysis_model.process_list
    for process in process_list:
        update_analysis_model_process_data(process)
        all_stack_data[process].read_data(start=all_stack_data[process].start,
                                          stop=all_stack_data[process].stop,
                                          text_filter=analysis_model.text_filter,
                                          selected_ids=analysis_model.selected_ids[process],
                                          base_case=analysis_model.reference_id)
    centred = (analysis_model.centred_scatter_plot == "centred")
    log_scale = analysis_model.log_scale
    if analysis_model.scatter_plot_type == "clusters":
        scatter_plot = get_cluster_plot(analysis_data, event1, event2, svgchart, centred, log_scale)
    else:
        scatter_plot = \
            get_hotspot_scatter_plot(analysis_data, event1, event2, svgchart, centred, 
                                     analysis_model.hotspots, log_scale)
    return scatter_plot


@AnalysisView.route('/update_cluster_parameters', methods=['GET', 'POST'])
def update_cluster_parameters():
    # Update chart when the cluster parameters have been changed
    global all_analysis_data
    global svgchart
    global analysis_model
    data = request.get_json()
    analysis_type = analysis_model.analysis_type
    analysis_data = all_analysis_data[analysis_type]
    num_clusters = data['num_clusters']
    analysis_model.num_clusters = num_clusters
    event1 = analysis_model.event1
    event2 = analysis_model.event2
    centred = (analysis_model.centred_scatter_plot == "centred")
    append_cluster_labels = (analysis_model.flamegraph_mode == "clusters")
    log_scale = analysis_model.log_scale
    xlower = analysis_model.xlower
    xupper = analysis_model.xupper
    ylower = analysis_model.ylower
    yupper = analysis_model.yupper
    num_clusters = int(analysis_model.num_clusters)
    analysis_model.cluster_labels = run_analysis(analysis_data, event1, event2, centred,
                                                 append_cluster_labels, log_scale, num_clusters=num_clusters,
                                                 xlower=xlower, xupper=xupper, ylower=ylower, yupper=yupper)
    scatter_plot = get_cluster_plot(analysis_data, event1, event2, svgchart, centred, log_scale)
    return scatter_plot


@AnalysisView.route('/update_scatter_plot_mode', methods=['GET', 'POST'])
def update_scatter_plot_mode():
    global all_analysis_data
    global svgchart
    global analysis_model
    data = request.get_json()
    mode = data["scatter_plot_mode"]
    if mode == "log":
        analysis_model.log_scale = True
    elif mode == "absolute":
        analysis_model.log_scale = False
    elif mode == "centred":
        analysis_model.centred_scatter_plot = True
    elif mode == "default":
        analysis_model.centred_scatter_plot = False
    elif mode == "hotspots":
        analysis_model.scatter_plot_type = "hotspots"
    elif mode == "clusters":
        analysis_model.scatter_plot_type = "clusters"
    analysis_model.centred_scatter_plot = data["scatter_plot_mode"]
    analysis_type = analysis_model.analysis_type
    analysis_data = all_analysis_data[analysis_type]
    event1 = analysis_model.event1
    event2 = analysis_model.event2
    centred = (analysis_model.centred_scatter_plot == "centred")
    log_scale = analysis_model.log_scale
    if analysis_model.scatter_plot_type == "clusters":
        append_cluster_labels = (analysis_model.flamegraph_mode == "clusters")
        num_clusters = int(analysis_model.num_clusters)
        analysis_model.cluster_labels = analysis_data.get_cluster_labels()
        analysis_model.cluster_labels = run_analysis(analysis_data, event1, event2, centred,
                                                     append_cluster_labels, log_scale, num_clusters=num_clusters)
        scatter_plot = get_cluster_plot(analysis_data, event1, event2, svgchart, centred, log_scale)
    else:
        if centred:
            reference_process = analysis_model.reference_process
        else:
            reference_process = []
        analysis_data.make_data(reference_process, centred=centred, log_scale=log_scale)
        scatter_plot = \
            get_hotspot_scatter_plot(analysis_data, event1, event2, svgchart, centred, 
                                     analysis_model.hotspots, log_scale)
    return scatter_plot


@AnalysisView.route('/update_all_charts', methods=['GET', 'POST'])
def update_all_charts():
    global svgchart
    global analysis_model
    analysis_type = analysis_model.analysis_type
    analysis_data = all_analysis_data[analysis_type]
    analysis_data.reset_stack_maps()
    analysis_model.process_list
    data = request.get_json()
    run_new_analysis = False
    if 'minx' in data:
        minx = data['minx']
        maxx = data['maxx']
        miny = data['miny']
        maxy = data['maxy']
        analysis_model.xlower = 0.95 * minx
        analysis_model.xupper = 1.05 * maxx
        analysis_model.ylower = 0.95 * miny
        analysis_model.yupper = 1.05 * maxy
    if 'text_filter' in data:
        match = data['text_filter']
        if re.match(".*\[\[cluster", match):
            match = match.rpartition("[[cluster")[0]
        analysis_model.text_filter = match
    if 'new_ref_id' in data:  # Add reference id if not already in flamegraph_ids
        analysis_model.reference_id = data['new_ref_id']
        for process in analysis_model.process_list:
            old_ids = all_stack_data[process].get_flamegraph_process_ids()
            ids = []
            add_id = True
            for process_id in old_ids:
                if process_id.label == analysis_model.reference_id:
                    add_id = False
                    analysis_model.flamegraph_event_type = process_id.event_type
                ids.append(process_id)
            if add_id:
                for process_id in analysis_model.selected_ids[process]:
                    if process_id.label == analysis_model.reference_id:
                        ids.append(process_id)
                        analysis_model.flamegraph_event_type = process_id.event_type
            all_stack_data[process].set_flamegraph_process_ids(ids)
        analysis_model.reference_event = get_event(analysis_model.reference_id)
        analysis_model.reference_job = get_job(analysis_model.reference_id)
        analysis_model.reference_process = get_process(analysis_model.reference_id)
        analysis_model.reference_pid = get_pid(analysis_model.reference_id)
        analysis_model.reference_tid = get_tid(analysis_model.reference_id)
        analysis_model.base_event_reference_id = make_label(analysis_model.reference_job,
                                                            analysis_model.reference_process,
                                                            analysis_model.base_event, analysis_model.reference_pid,
                                                            analysis_model.reference_tid)
    if 'process_ids' in data:
        base_event = analysis_model.base_event
        ids = all_stack_data[base_event].get_all_process_ids()
        analysis_model.base_event_selected_ids = []
        for process_id in ids:
            if process_id.label in data["process_ids"]:
                analysis_model.base_event_selected_ids.append(process_id)
        analysis_model.process_list = []
        for job in src.GlobalData.processes:
            for process in src.GlobalData.processes[job]:
                for process_id in analysis_model.base_event_selected_ids:
                    if job == process_id.job and process == process_id.process_name:
                        analysis_model.process_list.append(job + "_" + process)
                        break
        run_new_analysis = True
    if "base_event_reference_id" in data:
        analysis_model.base_event_reference_id = data["base_event_reference_id"]
        analysis_model.reference_job = get_job(analysis_model.base_event_reference_id)
        analysis_model.reference_process = get_process(analysis_model.base_event_reference_id)
        analysis_model.reference_pid = get_pid(analysis_model.base_event_reference_id)
        analysis_model.reference_tid = get_tid(analysis_model.base_event_reference_id)
    if "selected_clusters" in data:
        nc = int(data["num_clusters"])
        analysis_model.clusters = [str(i) for i in range(0, nc)]
        analysis_model.selected_clusters = []
        for cluster in analysis_model.clusters:
            if cluster in data["selected_clusters"]:
                analysis_model.selected_clusters.append(cluster)
    if "selected_events" in data:
        analysis_model.selected_events = []
        for event in src.GlobalData.loaded_cpu_definition.get_active_events():
            if event in data["selected_events"]:
                analysis_model.selected_events.append(event)
        analysis_model.process_list = []
        for job in src.GlobalData.processes:
            for process in src.GlobalData.processes[job]:
                for process_id in analysis_model.base_event_selected_ids:
                    if job == process_id.job and process == process_id.process_name:
                        analysis_model.process_list.append(job + "_" + process)
                        break
    if "reset_filters" in data:
        run_new_analysis = True
    if 'direction' in data:
        if data["direction"] == "next":
            analysis_model.hotspots += 10
        else:
            analysis_model.hotspots -= 10
    for process in analysis_model.process_list:
        if process in all_stack_data:
            update_analysis_model_process_data(process)
            all_stack_data[process].read_data(start=all_stack_data[process].start,
                                              stop=all_stack_data[process].stop,
                                              text_filter=analysis_model.text_filter,
                                              selected_ids=analysis_model.selected_ids[process],
                                              base_case=analysis_model.reference_id)
        else:
            all_stack_data[process] = StackData(src.GlobalData.results_files,
                                                src.GlobalData.local_data,
                                                src.GlobalData.loaded_cpu_definition,
                                                data_view="process",
                                                data_id=process,
                                                debug=src.GlobalData.debug,
                                                n_proc=src.GlobalData.n_proc)
            update_analysis_model_process_data(process)
            # Update process ids and reference id
            all_stack_data[process].set_selected_process_ids(analysis_model.selected_ids[process])
            all_stack_data[process].set_base_case("", analysis_model.selected_ids[process])
            ids = [all_stack_data[process].get_base_case_id()]
            all_stack_data[process].set_flamegraph_process_ids(ids)
        analysis_data.add_data(all_stack_data[process], process)
    purge(src.GlobalData.local_data, ".svg")
    event1 = analysis_model.event1
    event2 = analysis_model.event2
    raw_event1 = event_to_raw_event(analysis_model.event1, src.GlobalData.loaded_cpu_definition)
    raw_event2 = event_to_raw_event(analysis_model.event2, src.GlobalData.loaded_cpu_definition)
    centred = (analysis_model.centred_scatter_plot == "centred")
    append_cluster_labels = (analysis_model.flamegraph_mode == "clusters")
    log_scale = analysis_model.log_scale
    xlower = analysis_model.xlower
    xupper = analysis_model.xupper
    ylower = analysis_model.ylower
    yupper = analysis_model.yupper
    if run_new_analysis:
        analysis_model.cluster_labels = \
            run_analysis(analysis_data, event1, event2, centred, append_cluster_labels, log_scale)
    else:
        analysis_model.cluster_labels = analysis_data.get_cluster_labels()
        analysis_data.make_stack_map([int(i) for i in analysis_model.selected_clusters],
                                     append_cluster_labels=append_cluster_labels, event1=raw_event1, event2=raw_event2,
                                     xlower=xlower, xupper=xupper, ylower=ylower, yupper=yupper)
    if analysis_model.scatter_plot_type == "clusters":
        analysis_model.layout.scatter_plot = get_cluster_plot(analysis_data, event1,
                                                              event2, svgchart, centred, log_scale,
                                                              xlower=xlower, xupper=xupper,
                                                              ylower=ylower, yupper=yupper)
    else:
        analysis_model.layout.scatter_plot = get_hotspot_scatter_plot(analysis_data, event1, event2,
                                                                      svgchart, centred, 
                                                                      analysis_model.hotspots, log_scale, 
                                                                      xlower=xlower, xupper=xupper,
                                                                      ylower=ylower, yupper=yupper)
    analysis_model.layout.event_totals_chart, analysis_model.layout.event_totals_table = \
        get_barchart(analysis_model.process_list, analysis_model.hotspots, svgchart)
    analysis_model.layout.flamegraph = get_flamegraph(analysis_data, analysis_model.process_list,
                                                      analysis_model.flamegraph_mode,
                                                      flamegraph_event_type=analysis_model.flamegraph_event_type)
    if analysis_model.num_custom_event_ratios > 0:
        analysis_model.layout.event_ratios_chart = get_custom_barchart(analysis_model.process_list, svgchart)
    analysis_model.layout.reference_id = analysis_model.reference_id
    analysis_model.layout.reference_event = analysis_model.reference_event
    analysis_model.layout.base_event_reference_id = analysis_model.base_event_reference_id
    analysis_model.layout.event_name_ref = replace_operators(analysis_model.reference_event)
    analysis_model.layout.text_filter = analysis_model.text_filter
    return jsonify(analysis_model.layout.to_dict())


@AnalysisView.route('/update_flamegraph_ids', methods=['GET', 'POST'])
def update_flamegraph_ids():
    global svgchart
    global analysis_model
    process_list = analysis_model.process_list
    analysis_type = analysis_model.analysis_type
    analysis_data = all_analysis_data[analysis_type]
    data = request.get_json()
    flamegraph_id = data['flamegraph_id']
    for process in process_list:
        if flamegraph_id == "selected":
            ids = analysis_model.selected_ids[process]
        elif flamegraph_id == "reference":
            ids = [all_stack_data[process].get_base_case_id()]
        else:  # add/remove id from flamegraph ids
            old_ids = all_stack_data[process].get_flamegraph_process_ids()
            ids = []
            add_id = True
            for process_id in old_ids:
                if process_id.label == flamegraph_id:
                    add_id = False
                    analysis_model.flamegraph_event_type = process_id.event_type
                else:
                    ids.append(process_id)
            if add_id:
                for process_id in analysis_model.selected_ids[process]:
                    if process_id.label == flamegraph_id:
                        ids.append(process_id)
                        analysis_model.flamegraph_event_type = process_id.event_type
        all_stack_data[process].set_flamegraph_process_ids(ids)
    analysis_model.layout.flamegraph = get_flamegraph(analysis_data, process_list, analysis_model.flamegraph_mode,
                                                      flamegraph_event_type=analysis_model.flamegraph_event_type)
    return jsonify(analysis_model.layout.to_dict())


@AnalysisView.route('/update_source_code', methods=['GET', 'POST'])
def update_source_code():
    global analysis_model
    data = request.get_json()
    label = data["id"]
    source_symbol = data["source_symbol"]
    analysis_model.layout.source_code_table, analysis_model.layout.source_code_info, \
        analysis_model.layout.source_code_line = get_source_code(source_symbol, label)
    return jsonify(analysis_model.layout.to_dict())


@AnalysisView.route('/update_flamegraph_mode', methods=['GET', 'POST'])
def update_flamegraph_mode():
    global analysis_model
    analysis_type = analysis_model.analysis_type
    analysis_data = all_analysis_data[analysis_type]
    process_list = analysis_model.process_list
    data = request.get_json()
    analysis_model.flamegraph_mode = data['flamegraph_mode']
    append_cluster_labels = (analysis_model.flamegraph_mode == "clusters")
    raw_event1 = event_to_raw_event(analysis_model.event1, src.GlobalData.loaded_cpu_definition)
    raw_event2 = event_to_raw_event(analysis_model.event2, src.GlobalData.loaded_cpu_definition)
    xlower = analysis_model.xlower
    xupper = analysis_model.xupper
    ylower = analysis_model.ylower
    yupper = analysis_model.yupper
    analysis_data.make_stack_map([int(i) for i in analysis_model.selected_clusters],
                                 append_cluster_labels=append_cluster_labels, event1=raw_event1, event2=raw_event2,
                                 xlower=xlower, xupper=xupper, ylower=ylower, yupper=yupper)
    analysis_model.layout.flamegraph = get_flamegraph(analysis_data, process_list, analysis_model.flamegraph_mode)
    return jsonify(analysis_model.layout.to_dict())


def get_source_code(symbol, label):
    if re.match(".*\[\[cluster", symbol):
        symbol = symbol.rpartition("[[cluster")[0]
    job_id = get_job(label)
    for i in range(len(src.GlobalData.hpc_results)):
        if job_id == src.GlobalData.hpc_results[i].get_job_id():
            process_id = all_stack_data[analysis_model.reference_process].get_process_id_from_label(label)
            source_code_info = generate_source_code_info(symbol, src.GlobalData.hpc_results[i])
            source_code_table, source_code_line = \
                generate_source_code_table(all_stack_data[analysis_model.reference_process], process_id,
                                           symbol, src.GlobalData.hpc_results[i])
            return source_code_table, source_code_info, source_code_line
    source_code_table, source_code_info, source_code_line = generate_empty_table()
    return source_code_table, source_code_info, source_code_line

def get_barchart(process_list, hotspots, svg_chart):
    # Setup Bar Chart
    barchart_filename = timestamp("barchart.svg")
    output_file = src.GlobalData.local_data + os.sep + barchart_filename
    event_totals_chart_title = 'Total Event count for selected Events/Threads: Reference = {}'\
        .format(analysis_model.reference_id)
    output_event_type = "original"
    chart = svg_chart.generate_vertical_stacked_bar_chart_multiple_jobs(all_stack_data,
                                                                        process_list,
                                                                        analysis_model.reference_process,
                                                                        analysis_model.reference_id,
                                                                        start=hotspots,
                                                                        title=event_totals_chart_title,
                                                                        output_event_type=output_event_type,
                                                                        write_colourmap=True)
    chart.render_to_file(output_file)
    try:
        event_totals_table = chart.render_table(style=False, transpose=True, total=True)
    except Exception as e:
        event_totals_table = ""
    svgfile = src.GlobalData.local_data + os.sep + barchart_filename
    svgfile = os.path.relpath(svgfile, AnalysisView.template_folder)
    return svgfile, event_totals_table


def get_custom_barchart(process_list, svg_chart):
    custom_barchart_filename = timestamp("custom_barchart.svg")
    output_file = src.GlobalData.local_data + os.sep + custom_barchart_filename
    event_totals_chart_title = 'Total Event count for Event Ratios: Reference = {}'.format(analysis_model.reference_id)
    output_event_type = "custom_event_ratio"
    chart = svg_chart.generate_bar_chart_multiple_jobs(all_stack_data,
                                                       process_list,
                                                       title=event_totals_chart_title,
                                                       output_event_type=output_event_type)
    chart.render_to_file(output_file)
    svgfile = src.GlobalData.local_data + os.sep + custom_barchart_filename
    svgfile = os.path.relpath(svgfile, AnalysisView.template_folder)
    return svgfile


def get_analysis(analysis_type):
    # determine type of analysis, and create on first use
    new_analysis = analysis_type not in all_analysis_data
    if new_analysis:
        analysis_data = GeneralAnalysis()
        all_analysis_data['general'] = analysis_data
    else:
        analysis_data = all_analysis_data['general']
    cluster_events = {"All": [], "Ratios": []}  # Re-populate, as custom events may have been added
    for event in src.GlobalData.loaded_cpu_definition.get_active_events():
        if re.match(".* / .*", event):
            e1, par, e2 = event.partition(" / ")
            cluster_events["Ratios"].append([event_to_raw_event(e1, src.GlobalData.loaded_cpu_definition),
                                             event_to_raw_event(e2, src.GlobalData.loaded_cpu_definition)])
        else:
            cluster_events["All"].append(event_to_raw_event(event, src.GlobalData.loaded_cpu_definition))
    analysis_data.set_events(cluster_events)
    return analysis_data, cluster_events


def run_analysis(analysis_data, event1, event2, centred, append_cluster_labels, log_scale=False,
                 num_clusters=11, xlower=-sys.maxsize, xupper=sys.maxsize, ylower=-sys.maxsize, yupper=sys.maxsize):
    # Setup cluster plot
    global analysis_model
    if centred:
        reference_process = analysis_model.reference_process
    else:
        reference_process = []
    raw_event1 = event_to_raw_event(event1, src.GlobalData.loaded_cpu_definition)
    raw_event2 = event_to_raw_event(event2, src.GlobalData.loaded_cpu_definition)
    analysis_data.make_data(reference_process, centred=centred, log_scale=log_scale)
    analysis_data.calculate_ratios(num_clusters, raw_event1, raw_event2, xlower, xupper, ylower, yupper)
    n = analysis_data.get_num_clusters()
    analysis_model.clusters = [str(i) for i in range(0, n)]
    analysis_model.selected_clusters = analysis_model.clusters
    analysis_data.set_cluster_filter([int(i) for i in analysis_model.selected_clusters])
    analysis_data.make_stack_map([int(i) for i in analysis_model.selected_clusters],
                                 append_cluster_labels=append_cluster_labels, event1=raw_event1,
                                 event2=raw_event2, xlower=xlower, xupper=xupper, ylower=ylower, yupper=yupper)
    cluster_labels = analysis_data.get_cluster_labels()
    return cluster_labels


def get_flamegraph(analysis_data, process_list, mode, flamegraph_event_type="original"):
    # Setup flamegraph
    flamegraph_type = "plot_for_process"
    if mode == "clusters":
        colours = get_top_ten_colours()
        color_map = analysis_data.get_flamegraph_colour_map(colours)
    else:  # mode == "hotspots"
        color_map = svgchart.get_flamegraph_colour_map()
    first_process = True
    for process in process_list:
        write_flamegraph_stacks(all_stack_data[process], flamegraph_type, append=(not first_process),
                                output_event_type=flamegraph_event_type)
        if first_process:
            collapsed_stacks_filename = all_stack_data[process].get_collapsed_stacks_filename()
            first_process = False
    flamegraph_filename = timestamp("flamegraph.svg")
    flamegraph_description = {}
    if flamegraph_event_type == "custom_event_ratio":
        FlameGraph(src.GlobalData.local_data,
                   collapsed_stacks_filename,
                   flamegraph_filename,
                   description=flamegraph_description,
                   custom_event_ratio=True)
    else:  # original
        FlameGraph(src.GlobalData.local_data,
                   collapsed_stacks_filename,
                   flamegraph_filename,
                   description=flamegraph_description,
                   custom_event_ratio=False,
                   color_map=color_map)
    svgfile = src.GlobalData.local_data + os.sep + flamegraph_filename
    svgfile = os.path.relpath(svgfile, AnalysisView.template_folder)
    return svgfile


def get_cluster_plot(analysis_data, event1, event2, svg_chart, centred,
                     log_scale=False, xlower=None, xupper=None, ylower=None, yupper=None):
    cluster_plot_filename = timestamp("scatter_plot.svg")
    output_file = src.GlobalData.local_data + os.sep + cluster_plot_filename
    n = analysis_data.get_num_clusters()
    cluster_chart_title = event1 + " vs " + event2 + ": " + str(n) + " clusters"
    if log_scale:
        yt = "Log10(" + event1 + ")"
        xt = "Log10(" + event2 + ")"
    else:
        yt = event1
        xt = event2
    raw_event1 = event_to_raw_event(event1, src.GlobalData.loaded_cpu_definition)
    raw_event2 = event_to_raw_event(event2, src.GlobalData.loaded_cpu_definition)
    chart = svg_chart.generate_cluster_plot(analysis_data,
                                            analysis_model.process_list,
                                            raw_event1,
                                            raw_event2,
                                            centred,
                                            xlower=xlower,
                                            ylower=ylower,
                                            xupper=xupper,
                                            yupper=yupper,
                                            yt=yt,
                                            xt=xt,
                                            title=cluster_chart_title)
    chart.render_to_file(output_file)
    svgfile = src.GlobalData.local_data + os.sep + cluster_plot_filename
    svgfile = os.path.relpath(svgfile, AnalysisView.template_folder)
    return svgfile


def get_hotspot_scatter_plot(analysis_data, event1, event2, svg_chart, centred, hotspots,
                             log_scale=False, xlower=None, xupper=None, ylower=None, yupper=None):
    scatter_plot_filename = timestamp("scatter_plot.svg")
    output_file = src.GlobalData.local_data + os.sep + scatter_plot_filename
    cluster_chart_title = event1 + " vs " + event2 + ": hotspots"
    if log_scale:
        yt = "Log10(" + event1 + ")"
        xt = "Log10(" + event2 + ")"
    else:
        yt = event1
        xt = event2
    raw_event1 = event_to_raw_event(event1, src.GlobalData.loaded_cpu_definition)
    raw_event2 = event_to_raw_event(event2, src.GlobalData.loaded_cpu_definition)
    chart = svg_chart.generate_hotspot_scatter_plot(analysis_data,
                                                    analysis_model.process_list,
                                                    analysis_model.reference_process,
                                                    analysis_model.reference_id,
                                                    raw_event1,
                                                    raw_event2,
                                                    centred,
                                                    start=hotspots,
                                                    xlower=xlower,
                                                    ylower=ylower,
                                                    xupper=xupper,
                                                    yupper=yupper,
                                                    yt=yt,
                                                    xt=xt,
                                                    title=cluster_chart_title)
    chart.render_to_file(output_file)
    svgfile = src.GlobalData.local_data + os.sep + scatter_plot_filename
    svgfile = os.path.relpath(svgfile, AnalysisView.template_folder)
    return svgfile
