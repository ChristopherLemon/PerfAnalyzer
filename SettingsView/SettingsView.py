import json
import os
import re
import copy
from collections import OrderedDict

from flask import render_template, request, Blueprint

import src.GlobalData as GlobalData
from src.PerfEvents import (
    get_available_cpus,
    get_cpu_definition,
    modify_event_definitions,
    EventDefinition,
    initialise_cpu_definitions,
)
from SettingsView.SettingsModel import SettingsModel

layout = {}

SettingsView = Blueprint(
    "SettingsView", __name__, template_folder="templates", static_folder="static"
)


@SettingsView.route("/settings", methods=["GET", "POST"])
def settings():
    """Update profiler settings"""
    global status
    global layout
    status = "CPU: " + GlobalData.job_settings.cpu
    layout["Results"] = GlobalData.results_files
    if "events_btn" in request.form:
        event_map = GlobalData.selected_cpu_definition.get_available_event_map()
        GlobalData.job_settings.events = []
        GlobalData.job_settings.raw_events = []
        for event in GlobalData.selected_cpu_definition.get_available_events():
            if event in request.form:
                GlobalData.job_settings.events.append(event)
                GlobalData.job_settings.raw_events.append(event_map[event])
        raw_events = GlobalData.job_settings.raw_events
        GlobalData.selected_cpu_definition.set_active_events(raw_events)
    if "settings_btn" in request.form:
        GlobalData.job_settings.dt = float(request.form["dt"])
        GlobalData.job_settings.max_events_per_run = int(
            request.form["max_events_per_run"]
        )
        GlobalData.job_settings.proc_attach = int(request.form["proc_attach"])
    if "perf_events_btn" in request.form:
        events = OrderedDict()
        for name in request.form:
            match = re.search(r"(.*)_edit_(.*)", name)
            if match:
                event = match.group(1)
                field = match.group(2)
                if event not in events:
                    events[event] = {
                        "event": "",
                        "raw_event": "",
                        "event_group": "",
                        "event_unit": "",
                    }
                events[event][field] = request.form[name]
        event_definitions = []
        for event in events:
            event_name = events[event]["event"]
            raw_event = events[event]["raw_event"]
            event_group = events[event]["event_group"]
            event_unit = events[event]["event_unit"]
            event_definition = EventDefinition(
                event_name, raw_event, event_group, event_unit
            )
            event_definitions.append(event_definition)
        modify_event_definitions(GlobalData.job_settings.cpu, event_definitions)
        initialise_cpu_definitions()
        GlobalData.selected_cpu_definition = get_cpu_definition(
            GlobalData.job_settings.cpu
        )
        GlobalData.selected_cpu_definition.set_default_active_events()
    layout["title"] = "Settings " + status
    layout["footer"] = "Loaded Results: " + " & ".join(layout["Results"])
    return render_template(
        "settings.html",
        layout=layout,
        events=GlobalData.loaded_cpu_definition.get_active_events(),
        trace_jobs=GlobalData.trace_jobs,
        event_group_map=GlobalData.loaded_cpu_definition.get_active_event_group_map(),
        all_event_groups=GlobalData.loaded_cpu_definition.get_event_groups(),
        selected_cpu_events=GlobalData.selected_cpu_definition.get_available_events(),
        selected_cpu_event_group_map=GlobalData.selected_cpu_definition.get_available_event_group_map(),
        selected_cpu_event_groups=GlobalData.selected_cpu_definition.get_event_groups(),
        jobs=GlobalData.jobs,
        processes=GlobalData.processes,
        enabled_modes=GlobalData.enabled_modes,
        job_settings=GlobalData.job_settings.to_dict(),
        available_cpus=get_available_cpus(),
        event_definitions=GlobalData.selected_cpu_definition.get_event_definitions(),
    )


@SettingsView.route("/update_cpu", methods=["GET", "POST"])
def update_cpu():
    GlobalData.job_settings.cpu = request.form["cpu"]
    GlobalData.selected_cpu_definition = get_cpu_definition(GlobalData.job_settings.cpu)
    GlobalData.selected_cpu_definition.set_default_active_events()
    status = "CPU: " + GlobalData.job_settings.cpu
    layout["title"] = "Settings " + status
    return render_template(
        "settings.html",
        layout=layout,
        events=GlobalData.loaded_cpu_definition.get_active_events(),
        trace_jobs=GlobalData.trace_jobs,
        event_group_map=GlobalData.loaded_cpu_definition.get_active_event_group_map(),
        all_event_groups=GlobalData.loaded_cpu_definition.get_event_groups(),
        selected_cpu_events=GlobalData.selected_cpu_definition.get_available_events(),
        selected_cpu_event_group_map=GlobalData.selected_cpu_definition.get_available_event_group_map(),
        selected_cpu_event_groups=GlobalData.selected_cpu_definition.get_event_groups(),
        jobs=GlobalData.jobs,
        processes=GlobalData.processes,
        enabled_modes=GlobalData.enabled_modes,
        job_settings=GlobalData.job_settings.to_dict(),
        available_cpus=get_available_cpus(),
        event_definitions=GlobalData.selected_cpu_definition.get_event_definitions(),
    )


def initialise_empty_job_settings():
    cpu = GlobalData.job_settings.cpu
    job_settings = SettingsModel(cpu=cpu, set_defaults=False)
    return job_settings


def initialise_default_job_settings(cpu, cpu_definition):
    job_settings = SettingsModel(
        cpu=cpu, cpu_definition=cpu_definition, set_defaults=True
    )
    return job_settings


def save_job_data():
    # Save job settings to 'job'.settings file
    job_data = {}
    job_data[
        "working_directory_linux"
    ] = GlobalData.job_settings.working_directory_linux
    job_data["executable"] = GlobalData.job_settings.executable
    job_data["server"] = GlobalData.job_settings.server
    job_data["queue"] = GlobalData.job_settings.queue
    job_data["processes"] = GlobalData.job_settings.processes
    job_data["processes_per_node"] = GlobalData.job_settings.processes_per_node
    job_data["run_parallel"] = GlobalData.job_settings.run_parallel
    job_data["run_system_wide"] = GlobalData.job_settings.run_system_wide
    job_data["run_as_root"] = GlobalData.job_settings.run_as_root
    job_data["arguments"] = GlobalData.job_settings.arguments
    job_data["copy_files"] = GlobalData.job_settings.copy_files
    job_data["job_name"] = GlobalData.job_settings.job_name
    job_data["local_mpirun_params"] = GlobalData.job_settings.local_mpirun_params
    job_data["global_mpirun_params"] = GlobalData.job_settings.global_mpirun_params
    job_data["mpirun_version"] = GlobalData.job_settings.mpirun_version
    job_data["lsf_params"] = GlobalData.job_settings.lsf_params
    job_data["perf_params"] = GlobalData.job_settings.perf_params
    job_data["period"] = GlobalData.job_settings.period
    job_data["frequency"] = GlobalData.job_settings.frequency
    job_data["use_lsf"] = GlobalData.job_settings.use_lsf
    job_data["use_ssh"] = GlobalData.job_settings.use_ssh
    # only store path to the private key, but not the actual key or password
    job_data["private_key"] = GlobalData.job_settings.private_key
    job_data["username"] = GlobalData.job_settings.username
    job_data["use_mpirun"] = GlobalData.job_settings.use_mpirun
    job_data["env_variables"] = GlobalData.job_settings.env_variables
    job_data["bin_path"] = GlobalData.job_settings.bin_path
    job_data["lib_path"] = GlobalData.job_settings.lib_path
    job_data["preload"] = GlobalData.job_settings.preload
    job_data["cpu"] = GlobalData.job_settings.cpu
    job_data["events"] = GlobalData.job_settings.events
    job_data["dt"] = GlobalData.job_settings.dt
    job_data["max_events_per_run"] = GlobalData.job_settings.max_events_per_run
    job_data["proc_attach"] = GlobalData.job_settings.proc_attach
    job_data["raw_events"] = GlobalData.job_settings.raw_events
    json_file = (
        GlobalData.local_data + os.sep + GlobalData.job_settings.job_name + ".settings"
    )
    with open(json_file, "w") as f:
        json.dump(job_data, f, indent=4)


def restore_job_data(filename):
    # Restore settings from 'job'.settings file
    json_file = GlobalData.local_data + os.sep + filename
    with open(json_file, "r") as f:
        job_data = json.load(f)
    details = copy.deepcopy(GlobalData.job_settings)
    try:
        job_settings = initialise_empty_job_settings()
        for setting in job_data:
            if hasattr(job_settings, setting):
                setattr(job_settings, setting, job_data[setting])
        GlobalData.job_settings = job_settings
        cpu = GlobalData.job_settings.cpu
        GlobalData.selected_cpu_definition = get_cpu_definition(cpu)
        raw_events = GlobalData.job_settings.raw_events
        GlobalData.selected_cpu_definition.set_active_events(raw_events)
    except Exception as e:
        GlobalData.job_settings = details
        raise Exception(str(e))
