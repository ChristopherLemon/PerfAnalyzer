import os
import re
import errno
import logging
import webbrowser
import argparse
import pathlib
from tools.CustomLogging import setup_main_logger
from tools.HPCExperiment import HPCExperimentHandler, HPCResultsHandler, is_HPC_result
from werkzeug.utils import secure_filename
from tools.JobHandler import JobHandler, Job
from tools.ResultsHandler import get_results_info, get_jobs, get_cpu, get_run_summary
from tools.Utilities import purge, format_percentage, format_number, replace_operators, get_datetime, \
    get_datetime_diff, abs_path_to_rel_path, natural_sort
from plotting.RunSummaryTables import generate_run_summary_table
import tools.GlobalData
from tools.PerfEvents import get_cpu_definition, get_default_cpu, initialise_cpu_definitions
from multiprocessing import freeze_support
from io import StringIO
from flask import Flask, render_template, request, send_from_directory
from TraceView.TraceView import TraceView, reset_trace_view
from EventView.EventView import EventView, reset_event_view
from CustomEventsView.CustomEventsView import CustomEventsView
from ProcessView.ProcessView import ProcessView, reset_process_view
from AnalysisView.AnalysisView import AnalysisView, reset_analysis_view
from SettingsView.SettingsView import SettingsView, save_job_data, restore_job_data, initialise_default_job_settings

app = Flask(__name__)
tools.GlobalData.root_directory = app.root_path
tools.GlobalData.local_data = os.path.join(tools.GlobalData.root_directory, 'results')
UPLOAD_FOLDER = os.path.relpath(tools.GlobalData.local_data, os.getcwd())
ALLOWED_EXTENSIONS = set(['results', 'settings', 'xml'])

log_stream = StringIO()
submitted_jobs = []
main_logger = None
logfile = ""
raw_events = []
layout = {"Results": ["None"]}
status = ""
initialise = True


app.register_blueprint(TraceView, url_prefix='/trace')
app.register_blueprint(EventView, url_prefix='/event')
app.register_blueprint(ProcessView, url_prefix='/process')
app.register_blueprint(AnalysisView, url_prefix='/analysis')
app.register_blueprint(SettingsView, url_prefix='/settings')
app.register_blueprint(CustomEventsView, url_prefix='/custom_events')
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.jinja_env.filters['format_percentage'] = format_percentage
app.jinja_env.filters['replace_operators'] = replace_operators
app.jinja_env.filters['abs_path_to_rel_path'] = abs_path_to_rel_path
app.jinja_env.filters['natural_sort'] = natural_sort
app.config['PROPAGATE_EXCEPTIONS'] = True
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@app.context_processor
def utility_function():
    return {'format_number': format_number, 'abs_path_to_rel_path': abs_path_to_rel_path}


def reset_data_structures():
    global processes
    processes = []
    reset_event_view()
    reset_process_view()
    reset_analysis_view()
    reset_trace_view()


def initialise_app():
    global logfile
    global main_logger
    global status
    global layout
    if not os.path.exists(tools.GlobalData.local_data):
        try:
            os.makedirs(tools.GlobalData.local_data)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
    tools.GlobalData.perf_events = os.path.join(tools.GlobalData.root_directory, 'perf_events')
    logfile = tools.GlobalData.local_data + os.sep + "main.log"
    setup_main_logger(log_stream, logfile, 'main_logger', debug=tools.GlobalData.debug)
    main_logger = logging.getLogger("main_logger")
    reset_data_structures()
    try:
        initialise_cpu_definitions()
    except Exception as e:
        main_logger.info(u"Error loading perf event data. " + str(e))
        status = "Error reading perf event data"
    layout["title"] = "Submit Jobs / Load Profiles: " + status
    layout["footer"] = "Loaded Results: None"
    cpu = get_default_cpu()
    tools.GlobalData.selected_cpu_definition = get_cpu_definition(cpu)
    tools.GlobalData.selected_cpu_definition.set_default_active_events()
    tools.GlobalData.loaded_cpu_definition = get_cpu_definition(cpu)
    initialise_default_job_settings(cpu)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


def is_results_file(filename):
    found = '.' in filename and filename.rsplit('.', 1)[1] == 'results'
    return found

def is_HPC_experiment_file(filename):
    found = re.match(".*experiment.*\.xml", filename)
    return found


@app.route('/results/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
@app.route('/index', methods=['GET', 'POST'])
def index():
    # Request handler for job submission and results/settings loading
    global status
    global processes
    global layout
    global raw_events
    global main_logger
    global logfile
    global submitted_jobs
    global initialise
    if request.method == 'POST':
        # Load requested results - just check which events can be found in requested results files at this point
        load_perf_data = 'perf_btn' in request.form
        load_hpc_data = 'hpc_btn' in request.form
        load_profile_data = 'profile_btn' in request.form
        if load_profile_data or load_hpc_data or load_perf_data:
            experiment_file = None
            perf_data_files = []
            allfiles = request.files.getlist("file[]")
            reset_data_structures()
            for foundfile in allfiles:
                if foundfile.filename == '':
                    return render_template('index.html',
                                           layout=layout,
                                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                                           event_group_map=tools.GlobalData.loaded_cpu_definition
                                           .get_active_event_group_map(),
                                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                                           jobs=tools.GlobalData.jobs,
                                           processes=tools.GlobalData.processes,
                                           job_settings=tools.GlobalData.job_settings,
                                           enabled_modes=tools.GlobalData.enabled_modes)
                if (load_profile_data and allowed_file(foundfile.filename)) or load_hpc_data or load_perf_data:
                    filename = secure_filename(foundfile.filename)
                    if load_hpc_data:
                        if not os.path.exists(os.path.join(tools.GlobalData.local_data, foundfile.filename)):
                            path_to_dir = pathlib.Path(
                                pathlib.Path(tools.GlobalData.local_data) / pathlib.Path(foundfile.filename)).parent
                            pathlib.Path(path_to_dir).mkdir(parents=True, exist_ok=True)
                            try:
                                foundfile.save(str(path_to_dir / pathlib.Path(foundfile.filename).name))
                            except Exception as e:
                                main_logger.info(u" Failed copy: " + str(path_to_dir / pathlib.Path(foundfile.filename).name))
                        if is_HPC_experiment_file(foundfile.filename):
                            experiment_file = str(pathlib.Path(pathlib.Path(tools.GlobalData.local_data) / pathlib.Path(foundfile.filename)))
                    elif is_results_file(filename):
                        results_file = os.path.basename(foundfile.filename)
                        if results_file not in tools.GlobalData.results_files:
                            tools.GlobalData.results_files.append(filename)
                    elif load_perf_data:
                        perf_data_files.append(filename)
                        perf_working_directory = request.form['path_to_perf_data']

            if len(perf_data_files) > 0:
                jobhandler = JobHandler(tools.GlobalData.root_directory)
                results = jobhandler.convert_perf_data(perf_data_files, tools.GlobalData.local_data, perf_working_directory)
                tools.GlobalData.results_files.append(results)

            if experiment_file:
                analysis_level = request.form["analysis_level"]
                if re.match("Line", analysis_level):
                    include_loops = True
                    include_statements = True
                elif re.match("Loop", analysis_level):
                    include_loops = True
                    include_statements = False
                else:  # "Procedure"
                    include_loops = False
                    include_statements = False
                hpc_experiment = HPCExperimentHandler(tools.GlobalData.local_data, experiment_file)
                results = hpc_experiment.create_results(include_loops, include_statements)
                main_logger.info(u"Created HPC Experiment results: " + hpc_experiment.get_results_file_name()
                                 + " from Experiment " + hpc_experiment.get_experiment_file_name())
                results_file = os.path.basename(results)
                if results_file not in tools.GlobalData.results_files:
                    tools.GlobalData.results_files.append(results_file)
                tools.GlobalData.hpc_results.append(HPCResultsHandler(tools.GlobalData.local_data, results_file))
                main_logger.info(u"Loaded HPC Experiment results: " + results_file)
            else:
                for results_file in tools.GlobalData.results_files:
                    full_path = os.path.join(tools.GlobalData.local_data, results_file)
                    if is_HPC_result(full_path):
                        tools.GlobalData.hpc_results.append(HPCResultsHandler(tools.GlobalData.local_data, results_file))
                        main_logger.info(u"Loaded HPC Experiment results: " + results_file)

            purge(tools.GlobalData.local_data, "_compressed")
            layout["Results"] = tools.GlobalData.results_files
            main_logger.info(u"Loaded Results " + ", ".join(tools.GlobalData.results_files))
            tools.GlobalData.processes, raw_events = get_results_info(tools.GlobalData.local_data,
                                                                      tools.GlobalData.results_files)
            tools.GlobalData.cpu = get_cpu(tools.GlobalData.local_data, tools.GlobalData.results_files)
            tools.GlobalData.loaded_cpu_definition = get_cpu_definition(tools.GlobalData.cpu, raw_events)
            loaded_events = tools.GlobalData.loaded_cpu_definition.get_active_events()
            tools.GlobalData.jobs = get_jobs(tools.GlobalData.results_files)
            tools.GlobalData.enabled_modes = tools.GlobalData.loaded_cpu_definition.get_enabled_modes()
            main_logger.info(u"Found events: " + ", ".join(loaded_events))
            status = "Loaded " + " & ".join(layout["Results"])
            layout["title"] = status
            layout["footer"] = "Loaded Results: " + " & ".join(layout["Results"])

# Get settings from previously submitted job
        elif 'settings_btn' in request.form:
            foundfile = request.files.getlist("file")[0]
            if foundfile.filename == '':
                return render_template('index.html',
                                       layout=layout,
                                       jobs=tools.GlobalData.jobs,
                                       events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                                       event_group_map=tools.GlobalData.loaded_cpu_definition
                                       .get_active_event_group_map(),
                                       all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                                       processes=tools.GlobalData.processes,
                                       job_settings=tools.GlobalData.job_settings,
                                       enabled_modes=tools.GlobalData.enabled_modes)
            if foundfile and allowed_file(foundfile.filename):
                filename = secure_filename(foundfile.filename)
                if not os.path.exists(os.path.join(tools.GlobalData.local_data, filename)):
                    foundfile.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                layout["Settings"] = filename
            try:
                restore_job_data(layout["Settings"])
            except Exception as e:
                main_logger.info(u"Error loading settings - missing Data " + str(e))
                main_logger.info(u"Loaded Settings: Aborted")
                layout["footer"] = "Loaded Settings: Aborted"
            else:
                main_logger.info(u"Loaded Settings: " + layout["Settings"])
                status = "Loaded " + layout["Settings"]
                layout["title"] = status
                layout["footer"] = "Loaded Settings: " + layout["Settings"]

# Get details of job to be submitted, and submit job
        elif 'run_btn' in request.form:
            tools.GlobalData.job_settings["arguments"] = request.form["perf_args"]
            tools.GlobalData.job_settings["job_name"] = request.form["perf_job_name"]
            tools.GlobalData.job_settings["copy_files"] = request.form["copy_files"]
            if 'use_ssh' in request.form:
                tools.GlobalData.job_settings["use_ssh"] = True
                tools.GlobalData.job_settings["server"] = request.form["server"]
                tools.GlobalData.job_settings["username"] = request.form["username"]
                if 'password' in request.form:
                    tools.GlobalData.job_settings["password"] = request.form["password"]
                    tools.GlobalData.job_settings["private_key"] = ""
                else:
                    tools.GlobalData.job_settings["private_key"] = request.form["private_key"]
                    tools.GlobalData.job_settings["password"] = ""
            else:
                tools.GlobalData.job_settings["use_ssh"] = False
            if 'use_lsf' in request.form:
                tools.GlobalData.job_settings["use_lsf"] = True
                tools.GlobalData.job_settings["lsf_params"] = request.form["lsf_params"]
                tools.GlobalData.job_settings["queue"] = request.form["queue"]
                tools.GlobalData.job_settings["processes_per_node"] = int(request.form["processes_per_node"])
            else:
                tools.GlobalData.job_settings["use_lsf"] = False
                tools.GlobalData.job_settings["processes_per_node"] = 1
            if 'use_mpirun' in request.form:
                tools.GlobalData.job_settings["use_mpirun"] = True
                tools.GlobalData.job_settings["global_mpirun_params"] = request.form["global_mpirun_params"]
                tools.GlobalData.job_settings["local_mpirun_params"] = request.form["local_mpirun_params"]
                tools.GlobalData.job_settings["mpirun_version"] = request.form["mpirun_version"]
                tools.GlobalData.job_settings["processes"] = int(request.form["processes"])
            else:
                tools.GlobalData.job_settings["use_mpirun"] = False
                tools.GlobalData.job_settings["processes"] = 1
            tools.GlobalData.job_settings["run_parallel"] = ('run_parallel' in request.form)
            tools.GlobalData.job_settings["run_system_wide"] = ('run_system_wide' in request.form)
            tools.GlobalData.job_settings["run_as_root"] = ('run_as_root' in request.form)
            tools.GlobalData.job_settings["perf_params"] = request.form["perf_params"]
            tools.GlobalData.job_settings["frequency"] = request.form["frequency"]
            tools.GlobalData.job_settings["period"] = request.form["period"]
            tools.GlobalData.job_settings["working_directory_linux"] = request.form["working_directory_linux"]
            tools.GlobalData.job_settings["executable"] = request.form["executable"]
            tools.GlobalData.job_settings["env_variables"] = request.form["env_variables"]
            tools.GlobalData.job_settings["bin_path"] = request.form["bin_path"]
            tools.GlobalData.job_settings["lib_path"] = request.form["lib_path"]
            tools.GlobalData.job_settings["preload"] = request.form["preload"]
            status = 'Submitted Jobs: '
            main_logger.info(u"Preparing job " + tools.GlobalData.job_settings["job_name"])

            job = Job(tools.GlobalData.job_settings["job_name"],
                      tools.GlobalData.job_settings["copy_files"],
                      tools.GlobalData.job_settings["run_parallel"],
                      tools.GlobalData.job_settings["run_system_wide"],
                      tools.GlobalData.job_settings["run_as_root"],
                      tools.GlobalData.job_settings["processes"],
                      tools.GlobalData.job_settings["processes_per_node"],
                      tools.GlobalData.job_settings["executable"],
                      tools.GlobalData.job_settings["arguments"],
                      tools.GlobalData.job_settings["working_directory_linux"],
                      tools.GlobalData.job_settings["queue"],
                      tools.GlobalData.selected_cpu_definition,
                      tools.GlobalData.selected_cpu_definition.get_active_raw_events(),
                      tools.GlobalData.job_settings["period"],
                      tools.GlobalData.job_settings["frequency"],
                      tools.GlobalData.job_settings["dt"],
                      tools.GlobalData.job_settings["max_events_per_run"],
                      tools.GlobalData.job_settings["proc_attach"],
                      tools.GlobalData.job_settings["env_variables"],
                      tools.GlobalData.job_settings["bin_path"],
                      tools.GlobalData.job_settings["lib_path"],
                      tools.GlobalData.job_settings["preload"],
                      tools.GlobalData.job_settings["global_mpirun_params"],
                      tools.GlobalData.job_settings["local_mpirun_params"],
                      tools.GlobalData.job_settings["mpirun_version"],
                      tools.GlobalData.job_settings["lsf_params"],
                      tools.GlobalData.job_settings["perf_params"],
                      tools.GlobalData.job_settings["use_mpirun"],
                      tools.GlobalData.job_settings["use_lsf"],
                      tools.GlobalData.job_settings["use_ssh"])

            jobhandler = JobHandler(tools.GlobalData.root_directory, job)

            if tools.GlobalData.job_settings["use_ssh"]:
                e = jobhandler.check_connection(tools.GlobalData.job_settings)
                if e != "":
                    main_logger.info(u"Job " + tools.GlobalData.job_settings["job_name"] + ": " + e)
                    main_logger.info(u"Job " + tools.GlobalData.job_settings["job_name"] + " Aborted")
                    status = "Error - connection error"
                    layout["title"] = "Submit Jobs / Load Profiles: " + status
                    return render_template('index.html',
                                           layout=layout,
                                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                                           event_group_map=tools.GlobalData.loaded_cpu_definition
                                           .get_active_event_group_map(),
                                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                                           jobs=tools.GlobalData.jobs,
                                           processes=tools.GlobalData.processes,
                                           job_settings=tools.GlobalData.job_settings,
                                           enabled_modes=tools.GlobalData.enabled_modes)
            failed_paths = jobhandler.get_failed_paths(job, tools.GlobalData.job_settings)
            if len(failed_paths) > 0:
                for path in failed_paths:
                    main_logger.info(u"Job " + tools.GlobalData.job_settings["job_name"] + ": "
                                     + path + " was not found")
                main_logger.info(u"Job " + tools.GlobalData.job_settings["job_name"] + " Aborted")
                status = "Error - remote directory is invalid"
                layout["title"] = "Submit Jobs / Load Profiles: " + status
                return render_template('index.html',
                                       layout=layout,
                                       events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                                       event_group_map=tools.GlobalData.loaded_cpu_definition
                                       .get_active_event_group_map(),
                                       all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                                       jobs=tools.GlobalData.jobs,
                                       processes=tools.GlobalData.processes,
                                       job_settings=tools.GlobalData.job_settings,
                                       enabled_modes=tools.GlobalData.enabled_modes)
            main_logger.info(u"perf_event_paranoid: "
                             + jobhandler.check_perf_event_paranoid(tools.GlobalData.job_settings))
            main_logger.debug(u" Finished preparing scripts")
            main_logger.debug(u" Executing scripts")
            save_job_data()
            try:
                jobhandler.execute_perf(tools.GlobalData.job_settings)
            except Exception as e:
                main_logger.info(u"Error Running Perf Job. " + str(e))
            main_logger.debug(u" Finished executing scripts")
            status = "Submitted Job " + tools.GlobalData.job_settings["job_name"]
            layout["title"] = "Submit Jobs / Load Profiles: " + status
            layout["footer"] = "Loaded Results: " + " & ".join(layout["Results"])
            start_time = get_datetime()
            main_logger.info(u"Job " + tools.GlobalData.job_settings["job_name"] + " submitted at "
                             + start_time.strftime("%Y-%m-%d %H:%M:%S"))
            submitted_jobs.append({'job_name': tools.GlobalData.job_settings["job_name"], 'job_status': "running",
                                   "start_time": start_time})
            main_logger.info(u"Job " + tools.GlobalData.job_settings["job_name"] + " is running")

# Display
    if initialise:
        initialise_app()
        initialise = False
    else:
        status = ""
        layout["title"] = "Submit Jobs / Load Profiles: " + status
    return render_template('index.html',
                           layout=layout,
                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                           event_group_map=tools.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                           jobs=tools.GlobalData.jobs,
                           processes=tools.GlobalData.processes,
                           job_settings=tools.GlobalData.job_settings,
                           enabled_modes=tools.GlobalData.enabled_modes)


@app.route('/clear_loaded_data', methods=['GET', 'POST'])
def clear_loaded_data():
    reset_data_structures()
    cpu = get_default_cpu()
    tools.GlobalData.results_files = []
    tools.GlobalData.processes = []
    tools.GlobalData.hpc_results = []
    tools.GlobalData.enabled_modes = None
    tools.GlobalData.enabled_modes = {"roofline_analysis": False, "general_analysis": False}
    tools.GlobalData.loaded_cpu_definition = get_cpu_definition(cpu)
    layout["footer"] = "Loaded Results: None"
    layout["title"] = "Submit Jobs / Load Profiles: "
    return render_template('index.html',
                           layout=layout,
                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                           event_group_map=tools.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                           jobs=tools.GlobalData.jobs,
                           processes=tools.GlobalData.processes,
                           job_settings=tools.GlobalData.job_settings,
                           enabled_modes=tools.GlobalData.enabled_modes)


@app.route('/run_summary', methods=['GET', 'POST'])
def run_summary():
    layout["title"] = "Summary of Loaded Results"
    layout["footer"] = "Loaded Results: " + " & ".join(layout["Results"])
    event_counters, run_numbers, run_durations, run_parameters = get_run_summary(tools.GlobalData.local_data,
                                                                                 tools.GlobalData.results_files)
    run_summary_table = ""
    if len(tools.GlobalData.results_files)>0:
        run_summary_table = generate_run_summary_table(tools.GlobalData.loaded_cpu_definition, event_counters,
                                                       run_numbers, run_durations, run_parameters)
    return render_template('RunSummary.html',
                           layout=layout,
                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                           event_group_map=tools.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                           jobs=tools.GlobalData.jobs,
                           processes=tools.GlobalData.processes,
                           enabled_modes=tools.GlobalData.enabled_modes,
                           run_summary_table=run_summary_table)


@app.route('/check_for_results', methods=['GET', 'POST'])
def check_for_results():
    # Poll for finished job - check for existence of 'job'.done file
    global submitted_jobs
    global main_logger
    global log_stream
    job_durations = {}
    for job in submitted_jobs:
        job_name = job["job_name"]
        if job["job_status"] == "running":
            start_time = job["start_time"]
            time_now = get_datetime()
            duration = get_datetime_diff(time_now, start_time)
            filename = tools.GlobalData.local_data + os.sep + job["job_name"] + ".done"
            if os.path.isfile(filename):
                main_logger.info(u"Job " + job["job_name"] + " has finished at "
                                 + time_now.strftime("%Y-%m-%d %H:%M:%S") + " (" + str(duration) + ")")
                main_logger.info(u"Load perf profile " + job["job_name"] + ".results")
                job["job_status"] = "finished"
            else:
                job_durations[job_name] = str(duration)
    job_run_info = []
    if len(job_durations) > 0:
        job_run_info.append("Running Jobs:")
        for job_name in job_durations:
            job_run_info.append(job_name + " - " + job_durations[job_name])
    return log_stream.getvalue() + "\n".join(job_run_info)


@app.route('/clear_html_log', methods=['GET', 'POST'])
def clear_html_log():
    # Clear progress window
    global log_stream
    log_stream.truncate(0)
    return log_stream.getvalue()


@app.route('/about')
def about():
    return render_template('aboutword.html',
                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                           event_group_map=tools.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                           jobs=tools.GlobalData.jobs,
                           processes=tools.GlobalData.processes,
                           job_settings=tools.GlobalData.job_settings,
                           enabled_modes=tools.GlobalData.enabled_modes)


@app.route('/td')
def td():
    return render_template('td.html',
                           events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                           event_group_map=tools.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                           all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                           jobs=tools.GlobalData.jobs,
                           processes=tools.GlobalData.processes,
                           job_settings=tools.GlobalData.job_settings,
                           enabled_modes=tools.GlobalData.enabled_modes)


@app.route('/shutdown', methods=['GET', 'POST'])
def shutdown():
    shutdown_server()
    return 'Shutting down...  close window'


def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


if __name__ == "__main__":
    freeze_support()
    parser = argparse.ArgumentParser(description='Perf Profiler')
    parser.add_argument('-host', '--host', default="127.0.0.1", dest="host", help="Set host (default: 127.0.0.1)")
    parser.add_argument('-port', '--port', default="9999",  dest="port", help="Set port number (default: 9999)")
    parser.add_argument('-processes', '--processes', type=int, dest="n_proc", default=4,
                        help="Number of processes for processing results data (default: 4)")
    parser.add_argument('-debug', '--debug', action="store_true", default=False, dest="debug",
                        help="Output debug info")
    parser.add_argument('-browser', '--browser', default="default", dest="browser",
                        help="Path to web browser (default: system default web browser)")
    args = parser.parse_args()
    host = args.host
    port = args.port
    tools.GlobalData.debug = args.debug
    tools.GlobalData.n_proc = args.n_proc
    browser = args.browser
    url = "http://{}:{}/index".format(host, port)
    if browser == "default":
        webbrowser.open_new(url)
    else:
        browser_path = os.path.normpath(browser)
        webbrowser.register('custom_browser', None, webbrowser.BackgroundBrowser(browser_path), 1)
        webbrowser.get('custom_browser').open_new_tab(url)
    app.run(debug=False, use_reloader=False, host=host, port=int(port))


