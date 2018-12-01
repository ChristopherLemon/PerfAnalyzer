from flask import render_template, request, Blueprint
import tools.GlobalData
from tools.PerfEvents import get_available_cpus, get_cpu_definition, modify_event_definitions, EventDefinition, initialise_cpu_definitions, get_event_weights
from tools.JobHandler import get_global_mpirun_params, get_local_mpirun_params, get_perf_params, get_lsf_params, get_mpirun_appfile
from collections import OrderedDict
import json
import os
import re
import copy

layout = {}

SettingsView = Blueprint('SettingsView', __name__, template_folder='templates', static_folder='static')

@SettingsView.route('/settings', methods=['GET', 'POST'])
def settings():
# Update profiler settings
    global jobs
    global processes
    global status
    global layout
    status = "CPU: " + tools.GlobalData.user_settings["cpu"]
    layout["Results"] = tools.GlobalData.results_files
    if 'settings_btn' in request.form:
        event_map = tools.GlobalData.selected_cpu_definition.get_available_event_map()
        tools.GlobalData.user_settings["events"] = []
        tools.GlobalData.user_settings["raw_events"] = []
        for event in tools.GlobalData.selected_cpu_definition.get_available_events():
            if event in request.form:
                tools.GlobalData.user_settings["events"].append(event)
                tools.GlobalData.user_settings["raw_events"].append(event_map[event])
        raw_events = tools.GlobalData.user_settings["raw_events"]
        tools.GlobalData.selected_cpu_definition.set_active_events(raw_events)
        tools.GlobalData.user_settings["event_counter"] = int(request.form["event_counter"])
        tools.GlobalData.user_settings["frequency"] = int(request.form["frequency"])
        tools.GlobalData.user_settings["dt"] = float(request.form["dt"])
        tools.GlobalData.user_settings["max_events_per_run"] = int(request.form["max_events_per_run"])
        tools.GlobalData.user_settings["proc_attach"] = int(request.form["proc_attach"])
    if 'perf_events_btn' in request.form:
        events = OrderedDict()
        for name in request.form:
            match = re.search(r"(.*)_edit_(.*)", name)
            if match:
                event = match.group(1)
                field = match.group(2)
                if event not in events:
                    events[event] = {"event": "", "raw_event": "", "event_group": "", "event_unit": "",  "event_weight": 0}
                events[event][field] = request.form[name]
        event_definitions = []
        for event in events:
            event_name = events[event]["event"]
            raw_event = events[event]["raw_event"]
            event_group = events[event]["event_group"]
            event_unit = events[event]["event_unit"]
            event_counter = int(events[event]["event_weight"])
            event_definition = EventDefinition(event_name, raw_event, event_group, event_unit,
                                               event_counter)
            event_definitions.append(event_definition)
        modify_event_definitions(tools.GlobalData.user_settings["cpu"], event_definitions)
        initialise_cpu_definitions()
        tools.GlobalData.selected_cpu_definition = get_cpu_definition(tools.GlobalData.user_settings["cpu"])
        tools.GlobalData.selected_cpu_definition.set_default_active_events()
    layout["title"] = "Settings " + status
    layout["footer"] = "Loaded Results: " + " & ".join(layout["Results"])
    return render_template('settings.html',
                           layout=layout,
                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                           event_group_map=tools.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                           selected_cpu_events=tools.GlobalData.selected_cpu_definition.get_available_events(),
                           selected_cpu_event_group_map=tools.GlobalData.selected_cpu_definition.get_available_event_group_map(),
                           selected_cpu_event_groups=tools.GlobalData.selected_cpu_definition.get_event_groups(),
                           jobs=tools.GlobalData.jobs,
                           processes=tools.GlobalData.processes,
                           enabled_modes=tools.GlobalData.enabled_modes,
                           user_settings=tools.GlobalData.user_settings,
                           available_cpus=get_available_cpus(),
                           weights = get_event_weights(),
                           event_definitions=tools.GlobalData.selected_cpu_definition.get_event_definitions())


@SettingsView.route('/update_cpu', methods=['GET', 'POST'])
def update_cpu():
    tools.GlobalData.user_settings["cpu"] = request.form["cpu"]
    tools.GlobalData.selected_cpu_definition = get_cpu_definition(tools.GlobalData.user_settings["cpu"])
    tools.GlobalData.selected_cpu_definition.set_default_active_events()
    status = "CPU: " + tools.GlobalData.user_settings["cpu"]
    layout["title"] = "Settings " + status
    return render_template('settings.html',
                           layout=layout,
                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                           event_group_map=tools.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                           selected_cpu_events=tools.GlobalData.selected_cpu_definition.get_available_events(),
                           selected_cpu_event_group_map=tools.GlobalData.selected_cpu_definition.get_available_event_group_map(),
                           selected_cpu_event_groups=tools.GlobalData.selected_cpu_definition.get_event_groups(),
                           jobs=tools.GlobalData.jobs,
                           processes=tools.GlobalData.processes,
                           enabled_modes=tools.GlobalData.enabled_modes,
                           user_settings=tools.GlobalData.user_settings,
                           available_cpus=get_available_cpus(),
                           weights=get_event_weights(),
                           event_definitions=tools.GlobalData.selected_cpu_definition.get_event_definitions())

def initialise_default_user_settings(cpu):
    tools.GlobalData.user_settings = {}
    tools.GlobalData.job_settings = {}
    tools.GlobalData.user_settings["cpu"] = cpu
    tools.GlobalData.user_settings["events"] = tools.GlobalData.selected_cpu_definition.get_active_events()
    tools.GlobalData.user_settings["raw_events"] = []
    tools.GlobalData.user_settings["event_counter"] = 5000000
    tools.GlobalData.user_settings["frequency"] = 199
    tools.GlobalData.user_settings["dt"] = 50
    tools.GlobalData.user_settings["max_events_per_run"] = 4
    tools.GlobalData.user_settings["proc_attach"] = 1
    processes = 1
    processes_per_node = 1
    system_wide = False
    tools.GlobalData.job_settings["job_name"] = ""
    tools.GlobalData.job_settings["executable"] = ""
    tools.GlobalData.job_settings["arguments"] = ""
    tools.GlobalData.job_settings["processes"] = processes
    tools.GlobalData.job_settings["processes_per_node"] = processes_per_node
    tools.GlobalData.job_settings["global_mpirun_params"] = get_global_mpirun_params()
    tools.GlobalData.job_settings["local_mpirun_params"] = get_local_mpirun_params()
    tools.GlobalData.job_settings["mpirun_version"] = get_mpirun_appfile()
    tools.GlobalData.job_settings["lsf_params"] = get_lsf_params()
    tools.GlobalData.job_settings["perf_params"] = get_perf_params(system_wide)
    tools.GlobalData.job_settings["use_ssh"] = True
    tools.GlobalData.job_settings["use_lsf"] = True
    tools.GlobalData.job_settings["use_mpirun"] = True
    tools.GlobalData.job_settings["run_system_wide"] = system_wide
    tools.GlobalData.job_settings["run_as_root"] = False
    tools.GlobalData.job_settings["run_parallel"] = False
    tools.GlobalData.job_settings["server"] = ""
    tools.GlobalData.job_settings["queue"] = ""
    tools.GlobalData.job_settings["working_directory_linux"] = ""
    tools.GlobalData.job_settings["private_key"] = ""
    tools.GlobalData.job_settings["username"] = ""
    tools.GlobalData.job_settings["password"] = ""
    tools.GlobalData.job_settings["copy_files"] = ""
    tools.GlobalData.job_settings["env_variables"] = ""
    tools.GlobalData.job_settings["bin_path"] = ""
    tools.GlobalData.job_settings["lib_path"] = ""
    tools.GlobalData.job_settings["preload"] = ""


def initialise_empty_user_settings():
    cpu = tools.GlobalData.user_settings["cpu"]
    initialise_default_user_settings(cpu)
    for setting in tools.GlobalData.user_settings:
        tools.GlobalData.user_settings[setting] = None
    for setting in tools.GlobalData.job_settings:
        tools.GlobalData.job_settings[setting] = None


def save_job_data():
# Save job settings to 'job'.settings file
    job_data = {}
    job_data["working_directory_linux"] = tools.GlobalData.job_settings["working_directory_linux"]
    job_data["executable"] = tools.GlobalData.job_settings["executable"]
    job_data["server"] = tools.GlobalData.job_settings["server"]
    job_data["queue"] = tools.GlobalData.job_settings["queue"]
    job_data["processes"] = tools.GlobalData.job_settings["processes"]
    job_data["processes_per_node"] = tools.GlobalData.job_settings["processes_per_node"]
    job_data["run_parallel"] = tools.GlobalData.job_settings["run_parallel"]
    job_data["run_system_wide"] = tools.GlobalData.job_settings["run_system_wide"]
    job_data["run_as_root"] = tools.GlobalData.job_settings["run_as_root"]
    job_data["arguments"] = tools.GlobalData.job_settings["arguments"]
    job_data["copy_files"] = tools.GlobalData.job_settings["copy_files"]
    job_data["job_name"] = tools.GlobalData.job_settings["job_name"]
    job_data["local_mpirun_params"] = tools.GlobalData.job_settings["local_mpirun_params"]
    job_data["global_mpirun_params"] = tools.GlobalData.job_settings["global_mpirun_params"]
    job_data["mpirun_version"] = tools.GlobalData.job_settings["mpirun_version"]
    job_data["lsf_params"] = tools.GlobalData.job_settings["lsf_params"]
    job_data["perf_params"] = tools.GlobalData.job_settings["perf_params"]
    job_data["use_lsf"] = tools.GlobalData.job_settings["use_lsf"]
    job_data["use_ssh"] = tools.GlobalData.job_settings["use_ssh"]
    job_data["private_key"] = tools.GlobalData.job_settings["private_key"] # only store path to the private key, but not the actual key or password
    job_data["username"] = tools.GlobalData.job_settings["username"]
    job_data["use_mpirun"] = tools.GlobalData.job_settings["use_mpirun"]
    job_data["env_variables"] = tools.GlobalData.job_settings["env_variables"]
    job_data["bin_path"] = tools.GlobalData.job_settings["bin_path"]
    job_data["lib_path"] = tools.GlobalData.job_settings["lib_path"]
    job_data["preload"] = tools.GlobalData.job_settings["preload"]
    job_data["cpu"] = tools.GlobalData.user_settings["cpu"]
    job_data["event_counter"] = tools.GlobalData.user_settings["event_counter"]
    job_data["frequency"] = tools.GlobalData.user_settings["frequency"]
    job_data["events"] = tools.GlobalData.user_settings["events"]
    job_data["dt"] = tools.GlobalData.user_settings["dt"]
    job_data["max_events_per_run"] = tools.GlobalData.user_settings["max_events_per_run"]
    job_data["proc_attach"] = tools.GlobalData.user_settings["proc_attach"]
    job_data["raw_events"] = tools.GlobalData.user_settings["raw_events"]
    if 'run_duration' in tools.GlobalData.job_settings:
        job_data["run_duration"] = tools.GlobalData.job_settings["run_duration"]
    json_file = tools.GlobalData.local_data + os.sep + tools.GlobalData.job_settings["job_name"] + '.settings'
    with open(json_file, 'w') as f:
        json.dump(job_data, f, indent=4)


def restore_job_data(filename):
# Restore settings from 'job'.settings file
    json_file = tools.GlobalData.local_data + os.sep + filename
    with open(json_file, 'r') as f:
        job_data = json.load(f)
    details = copy.deepcopy(tools.GlobalData.job_settings)
    settings = copy.deepcopy(tools.GlobalData.user_settings)
    try:
        initialise_empty_user_settings()
        for setting in job_data:
            if setting in tools.GlobalData.job_settings:
                tools.GlobalData.job_settings[setting] = job_data[setting]
            elif setting in tools.GlobalData.user_settings:
                tools.GlobalData.user_settings[setting] = job_data[setting]
        cpu = tools.GlobalData.user_settings["cpu"]
        tools.GlobalData.selected_cpu_definition = get_cpu_definition(cpu)
        raw_events = tools.GlobalData.user_settings["raw_events"]
        tools.GlobalData.selected_cpu_definition.set_active_events(raw_events)
        if 'run_duration' in job_data:
            tools.GlobalData.job_settings["run_duration"] = job_data['run_duration']
    except Exception as e:
        tools.GlobalData.job_settings = details
        tools.GlobalData.user_settings = settings
        raise Exception(str(e))

