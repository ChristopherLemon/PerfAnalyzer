import io
import os
import re
from tools.Utilities import natural_sort
from collections import OrderedDict
from tempfile import mkstemp
from shutil import move
from os import remove, close

def modify_process_ids(orig_pid, orig_file):
# Replace process and thread ids with sets of sequential ids, starting from zero
    threads = {}
    process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
    with open(orig_file,'r') as result:
        for line in result:
            match = re.search(process_id_regex, line)
            if match:
                tid = match.group(3)
                if tid not in threads:
                    threads[tid] = tid
    sorted_threads = OrderedDict(natural_sort(threads.items(), key=lambda t: t[1]))
    tids = OrderedDict()
    n = 0
    for t in sorted_threads:
        if t == "all":
            tids[t] = t
        else:
            tids[t] = str(n)
            n += 1
    fh, abs_path = mkstemp()
    with open(abs_path,'wb') as new_file:
        with open(orig_file,'r') as result:
            for line in result:
                match = re.search(process_id_regex, line)
                if match:
                    pid = match.group(2)
                    tid = match.group(3)
                    l = re.sub("/" + tid,"/" + tids[tid], line)
                    l = re.sub(pid + "/",orig_pid + "/", l)
                    new_file.write(l.encode())
                else:
                    new_file.write(line.encode())
    close(fh)
    remove(orig_file)
    move(abs_path, orig_file)


def modify_system_wide_process_ids(orig_file):
# Replace process and thread ids with sets of sequential ids, starting from zero
# split data files for each host into separate files for each physical core
    threads = []
    host = re.findall("host(\d+)_",orig_file)[0][0]
    process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
    with open(orig_file, 'r') as result:
        for line in result:
            match = re.search(process_id_regex, line)
            if match:
                pid = match.group(2)
                tid = match.group(3)
                if not tid in threads:
                    threads.append(tid)
    sorted_threads = natural_sort(threads)
    tids = OrderedDict()
    n = 0
    for t in sorted_threads:
        if t == "all":
            tids[t] = t
        else:
            tids[t] = str(n)
            n += 1
    fs = {}
    last_time = ""
    with open(orig_file, 'r') as result:
        for line in result:
            match = re.search(process_id_regex, line)
            if match:
                pid = match.group(2)
                tid = match.group(3)
                l = re.sub("/" + tid, "/" + tids[tid], line)
                new_file = re.sub("host" + host, "host" + host + "_proc" + pid, orig_file)
                if new_file not in fs:
                    fs[new_file] = open(new_file, 'wb')
                    fs[new_file].write(last_time.encode())
                fs[new_file].write(l.encode())
            elif line[0:2] == "t=":
                last_time = line
                for f in fs:
                    fs[f].write(line.encode())
    for f in fs:
        fs[f].close()
    remove(orig_file)

def get_run_duration(stack_file):
# read last line of stacks file to get the last time recorded. i.e. t=10.0
    fs = open(stack_file, 'rb')
    file_size = os.path.getsize(stack_file)
    if file_size < 1000:
        last_line = fs.readlines()[-1].decode('ascii')
    else:
        max_line_length = 30
        fs.seek(-max_line_length, os.SEEK_END)
        last_line = fs.readlines()[-1].decode('ascii')
    t = 0.0
    if last_line[0:2] == "t=":
        t = last_line.rstrip().partition("=")[2]
        t = float(t)
    return t


def replace_results_file(local_data, results_file, job_id):
# Create new results file for system wide monitoring, with one file per core (for each event)
    fh, abs_path = mkstemp()
    with open(abs_path, 'wb') as new_results_file:
        with open(results_file, 'r') as result:
            for line in result:
                if (re.match("event_counter", line) or
                    re.match("time_interval", line) or
                    re.match("cpu_id", line) or
                    re.match("system_wide", line)): # copy run settings at start of results file
                    new_results_file.write(line.encode())
                else: # ignore original results files
                    break
        for f in os.listdir(local_data):
            if re.search(job_id + "_host(\d+)_proc",f): # populate new file with seperate results for each process
                fname = f + "\n"
                new_results_file.write(fname.encode())
    close(fh)
    remove(results_file)
    move(abs_path, results_file)

def get_events(path, results_files):  # Read events from results files
    events = []
    for result_file in results_files:
        full_filename = os.path.join(path, result_file)
        with open(full_filename) as infile:
            for line in infile:
                if not (re.match("event_counter", line) or
                            re.match("time_interval", line) or
                            re.match("cpu_id", line) or
                            re.match("system_wide", line)):
                    match = re.match("(.*proc(all|[0-9]+))_(.*)", line.strip())
                    event = match.group(3)
                    if event not in events:
                        events.append(event)
    events = natural_sort(events)
    return events

def get_processes(path, results_files): # Read processes from results files
    processes = []
    for result_file in results_files:
        full_filename = os.path.join(path, result_file)
        with open(full_filename) as infile:
            for line in infile:
                if not (re.match("event_counter", line) or
                        re.match("time_interval", line) or
                        re.match("cpu_id", line) or
                        re.match("system_wide", line)):
                    match = re.match("(.*proc(all|[0-9]+))_(.*)", line.strip())
                    name = match.group(1)
                    if name not in processes:
                        processes.append(name)
    processes = natural_sort(processes)
    return processes

def get_process_to_event_map(path, results_file):  # Get a process to event map, from a results file
    found = {}
    full_filename = os.path.join(path, results_file)
    with open(full_filename) as infile:
        for line in infile:
            if not (re.match("event_counter", line) or
                        re.match("time_interval", line) or
                        re.match("cpu_id", line) or
                        re.match("system_wide", line)):
                match = re.match("(.*proc(all|[0-9]+))_(.*)", line.strip())
                name = match.group(1)
                event = match.group(3)
                if re.search("trace", event): # skip trace events
                    continue
                if name in found:
                    found[name].append(event)
                else:
                    found[name] = [event]
    return found

def get_jobs(results_files):  # Read jobs from results file
    jobs = []
    for result_file in results_files:
        job = result_file.partition(".results")[0]
        jobs.append(job)
    jobs = natural_sort(jobs)
    return jobs

def get_job_name(result_file):
    return result_file.partition(".results")[0]

def get_event_counters(path, results_files):
    event_counters = {}
    for result_file in results_files:
        full_filename = os.path.join(path, result_file)
        job = get_job_name(result_file)
        if job not in event_counters:
            event_counters[job] = {}
        with open(full_filename) as infile:
            for line in infile:
                if re.match("event_counter", line):
                    # i.e. event_counter-cycles:run-1:100
                    match = re.match("event_counter-(.*):run-[0-9]+:([0-9]+)", line)
                    raw_event = match.group(1)
                    event_counter = match.group(2)
                    event_counters[job][raw_event] = int(event_counter)
    return event_counters

def get_run_summary(path, results_files):
    run_durations = {}
    run_numbers = {}
    event_counters = {}
    run_parameters = {}
    for result_file in results_files:
        full_filename = os.path.join(path, result_file)
        job = get_job_name(result_file)
        if job not in run_durations:
            run_durations[job] = {}
            run_numbers[job] = {}
            event_counters[job] = {}
            run_parameters[job] = {}
            run_parameters[job]["system_wide"] = False
        with open(full_filename) as infile:
            for line in infile:
                if re.match("event_counter", line):
                    # event-counter-cycles:run-1:100
                    event_string, run_string, event_counter = line.split(":")
                    raw_event = event_string.partition('-')[2]
                    run_number = run_string.partition('-')[2]
                    run_numbers[job][raw_event] = run_number
                    event_counters[job][raw_event] = int(event_counter)
                elif re.match("time_interval", line):
                    run_parameters[job]["time_interval"] = float(line.partition(":")[2])
                elif re.match("cpu_id", line):
                    run_parameters[job]["cpu_id"] = line.strip().partition(":")[2]
                elif re.match("system_wide", line):
                    run_parameters[job]["system_wide"] = True
                else:
                    job_process, par, raw_event = line.strip().rpartition('_')
                    if raw_event in run_numbers[job]:
                        run_number = str(run_numbers[job][raw_event])
                        filename = path + os.sep + line.strip()
                        t = get_run_duration(filename)
                        if run_number not in run_durations[job]:
                            run_durations[job][run_number] = t
                        else:
                            run_durations[job][run_number] = max(run_durations[job][run_number],t)
    return event_counters, run_numbers, run_durations, run_parameters

def get_cpu(path, results_files):
    for result_file in results_files:
        full_filename = os.path.join(path, result_file)
        with open(full_filename) as infile:
            for line in infile:
                if re.match("cpu_id", line):
                    cpu = line.strip().partition(":")[2]
                    return cpu

def get_results_info(path, results_files):  # Read processes from results file
    job_process_map = OrderedDict()
    processes = {}
    jobs = []
    raw_events = []
    for result_file in results_files:
        full_filename = os.path.join(path, result_file)
        job = result_file.rpartition(".results")[0]
        jobs.append(job)
        processes[job] = []
        with open(full_filename) as infile:
            for line in infile:
                if not (re.match("event_counter", line) or
                            re.match("time_interval", line) or
                            re.match("cpu_id", line) or
                            re.match("system_wide", line)):
                    match = re.match("(.*proc(all|[0-9]+))_(.*)", line.strip())
                    job_process = match.group(1)
                    event = match.group(3)
                    process = re.sub(job + "_", "", job_process)
                    job = job.partition("_proc")[0]
                    if process not in processes[job]:
                        processes[job].append(process)
                    if event not in raw_events:
                        raw_events.append(event)
        processes[job] = natural_sort(processes[job])
    jobs = natural_sort(jobs)
    for job in jobs:
        job_process_map[job] = processes[job]
    raw_events = natural_sort(raw_events)
    return job_process_map, raw_events
