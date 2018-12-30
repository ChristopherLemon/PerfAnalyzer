__author__ = 'CLemon'
import os
import re
import sys
import multiprocessing as mp
import pickle
from timeit import default_timer as timer
from tools.Utilities import natural_sort
from tools.CustomEvents import event_to_raw_event, raw_event_to_event, get_event_type, \
    create_custom_event_stack, is_composite_event
from collections import OrderedDict, defaultdict
from tools.ResultsHandler import get_job_name, get_event_counters


def get_job(task_or_label):
    """Get job from task_id or label, where
    task_id = job_processor_event, and
    label = task_id + "-pid:" + pid + "-tid:" + tid"""
    job = re.sub("_proc[0-9]+_.*", "", task_or_label)
    job = re.sub("_procall_.*", "", job)
    job = re.sub("_host[0-9]+", "", job)
    return job


def get_process(task_or_label):
    """Get processor from task_id or label, where
    task_id = job_processor_event, and
    label = task_id + "-pid:" + pid + "-tid:" + tid"""
    job = get_job(task_or_label)
    process = re.sub(job + "_", "", task_or_label).rpartition("_")[0]
    return process


def get_event(task_or_label):
    """Get event from task_id or label, where
    task_id = job_processor_event, and
    label = task_id + "-pid:" + pid + "-tid:" + tid"""
    job = get_job(task_or_label)
    process = get_process(task_or_label)
    event = re.sub(job + "_" + process + "_", "", task_or_label).partition("-pid")[0]
    return event


def get_pid(task_or_label):
    """Get pid from task_id or label, where
    task_id = job_processor_event, and
    label = task_id + "-pid:" + pid + "-tid:" + tid"""
    pid = task_or_label.rpartition("-pid:")[2].rpartition("-tid:")[0]
    return pid


def get_tid(task_or_label):
    """Get tid name from task_id or label, where
    task_id = job_processor_event, and
    label = task_id + "-pid:" + pid + "-tid:" + tid"""
    tid = task_or_label.rpartition("-tid:")[2]
    return tid


def make_label(job, processor, event, pid, tid):
    """make unique label from job, processor, event, pid and tid.
    Each label identifies an object representing collapsed stacks
    for a a specific job, event, process, and thread.
    task_id = job_processor_event, and
    label = task_id + "-pid:" + pid + "-tid:" + tid"""
    label = job + "_" + processor + "_" + event + "-pid:" + pid + "-tid:" + tid
    return label


def multi_run_wrapper(args):
        return worker(*args)


def worker(task, start_time, stop_time):
    task.execute(start_time, stop_time)
    task.write_stacks()
    pickle.dump(task, open(task.filename + ".p", "wb"))
    task.clear
    return


class StackDataID:
    """Metadata for collapsed stacks data for a specific job, event, process, and thread."""

    def __init__(self, job, label, task_id, pid, tid, process_name, event_name, raw_event, event_type):
        self.job = job
        self.label = label
        self.task_id = task_id
        self.pid = pid
        self.tid = tid
        self.event_type = event_type
        self.event_name = event_name
        self.raw_event = raw_event
        self.process_name = process_name
        self.count1 = 0
        self.count2 = 0
        self.total_percentage = 0.0
        self.max_percentage = 0.0


class ReadStacksTask:

    def __init__(self, task_id, filename, job, process_name, event, raw_event,
                 event_type, counter, time_interval):
        self.task_id = task_id
        self.filename = filename
        self.job = job
        self.process_name = process_name
        self.event = event
        self.raw_event = raw_event
        self.event_type = event_type
        self.event_counter = counter
        self.time_interval = time_interval
        self.work = {}
        self.stacks = {}
        self.X = {}
        self.Y = {}
        self.count = {}

    def execute(self, start_time, stop_time):
        file = self.filename
        event_type = self.event_type
        time = -1.0
        process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
        with open(file) as infile:
            for line in infile:
                line = line.strip()
                if line[0:2] == "t=":
                    t = line.partition("=")[2]
                    time = float(t)
                    self.update_timelines(event_type, time)
                    if start_time < time <= stop_time:
                        self.update_stacks(event_type)
                    for pid in self.count:
                        for tid in self.count[pid]:
                            self.count[pid][tid] = [0, 0]
                elif start_time <= time <= stop_time:
                    stack = line
                    if event_type == "custom_event_ratio":
                        stack, par, secondary = stack.rpartition(' ')
                    stack, par, primary = stack.rpartition(' ')
                    match = re.search(process_id_regex, line)
                    if match:
                        pid = match.group(2)
                        tid = match.group(3)
                        if pid not in self.count:
                            self.work[pid] = {}
                            self.count[pid] = {}
                        if tid not in self.count[pid]:
                            self.work[pid][tid] = OrderedDict()
                            self.count[pid][tid] = [0, 0]
                        if stack:
                            c0 = int(primary)
                            if event_type == "custom_event_ratio":
                                c1 = int(secondary)
                            else:
                                c1 = c0
                            self.count[pid][tid][0] += c0
                            self.count[pid][tid][1] += c1
                            if stack in self.work[pid][tid]:
                                self.work[pid][tid][stack][0] += c0
                                self.work[pid][tid][stack][1] += c1
                            else:
                                self.work[pid][tid][stack] = [c0, c1]

    def update_stacks(self, event_type):
        for pid in self.work:
            if pid in self.X:
                for tid in self.work[pid]:
                    if tid in self.X[pid]:
                        if len(self.X[pid][tid]) > 0:
                            c0 = self.count[pid][tid][0]
                            if c0 > 0:
                                if pid not in self.stacks:
                                    self.stacks[pid] = {}
                                if tid not in self.stacks[pid]:
                                    self.stacks[pid][tid] = OrderedDict()
                                for stack in self.work[pid][tid]:
                                    if event_type == "custom_event_ratio":
                                        if stack not in self.stacks[pid][tid]:
                                            self.stacks[pid][tid][stack] = [0, 0]
                                        self.stacks[pid][tid][stack][0] += self.work[pid][tid][stack][0]
                                        self.stacks[pid][tid][stack][1] += self.work[pid][tid][stack][1]
                                    else:
                                        if stack not in self.stacks[pid][tid]:
                                            self.stacks[pid][tid][stack] = [0, 0]
                                        self.stacks[pid][tid][stack][0] += self.work[pid][tid][stack][0]
                                self.work[pid][tid] = {}

    def update_timelines(self, event_type, time):
        for pid in self.count:
            if pid not in self.X:
                self.X[pid] = {}
                self.Y[pid] = {}
            for tid in self.count[pid]:
                if tid not in self.X[pid]:
                    self.X[pid][tid] = [0.0]
                    self.Y[pid][tid] = [0.0]
                c0 = self.count[pid][tid][0]
                c1 = self.count[pid][tid][1]
                if c0 > 0:
                    self.X[pid][tid].append(time)
                    if event_type == "custom_event_ratio":
                        if c1 > 0:
                            r = float(c0) / float(c1)
                        else:
                            r = 0.0
                    else:
                        if len(self.X[pid][tid]) > 1:
                            dt = self.X[pid][tid][-1] - self.X[pid][tid][-2]
                        else:
                            dt = time
                        r = float(self.event_counter)*float(c0) / dt
                    self.Y[pid][tid].append(r)

    def write_stacks(self):
        output_file = self.filename + "_compressed"
        f = open(output_file, 'wb')
        for pid in self.stacks:
            for tid in self.stacks[pid]:
                for stack in self.stacks[pid][tid]:
                    if self.event_type == "custom_event_ratio":
                        out = stack + ' ' + str(self.stacks[pid][tid][stack][0]) \
                              + ' ' + str(self.stacks[pid][tid][stack][1]) + '\n'
                    else:
                        out = stack + ' ' + str(self.stacks[pid][tid][stack][0]) + '\n'
                    f.write(out.encode())
        f.close()
        self.stacks = {}
        self.work = {}

    def clear(self):
        self.X = {}
        self.Y = {}
        self.work = {}
        self.stacks = {}


class StackData:
    """Object representing collapsed stack data for multiple data sets.
    For the event view the object holds data for the event across all
    loaded jobs, processes and threads.
    For the process view, the object holds data for for the process
    across all events and threads.
    Stack data can be processed by multiple processes."""

    def __init__(self, results_files, path, cpu_definition, data_view="event", data_id="", debug=True, n_proc=4):
        self.selected_ids = []
        self.all_jobs = []
        self.start = -1.0
        self.cpu_definition = cpu_definition
        self.results_files = results_files
        self.stack_file = ""
        self.event_counters = {}
        self.path = path
        self.system_wide = False
        self.data_view = data_view
        self.min_x = sys.float_info.max
        self.max_x = -sys.float_info.max
        self.min_y = sys.float_info.max
        self.max_y = -sys.float_info.max
        self.time_interval = 0.0
        self.cpu = ""
        self.tasks = OrderedDict()
        self.stacks = {}
        self.filtered_stacks = {}
        self.filtered_stacks_x = {}
        self.filtered_stacks_y = {}
        self.stack_map = None
        self.X = {}
        self.Y = {}
        self.work = {}
        self.count = {}
        self.totals = {}
        self.event_counters = get_event_counters(path, results_files)
        self.collapsed_stacks_filename = "data_stacks_collapsed"
        self.initial_count = 0
        if data_view == "event":  # Load a single event for all jobs, processes and threads
            self.event = event_to_raw_event(data_id, self.cpu_definition)
            self.process = None
            if is_composite_event(self.event):
                create_custom_event_stack(self, results_files, self.event)
                self.event_counters = get_event_counters(path, results_files)  # Update counters with new custom event
        if data_view == "process":  # Load all events\threads for a single process
            self.process = data_id
            self.event = None
        self.ordered_ids = []
        self.default_ids = []
        self.debug = debug
        self.n_proc = n_proc
        if debug:
            start = timer()
        self.read_data(initialise=True)  # Read all data on the first pass
        if debug:
            end = timer()
            print("Time to load data: " + str(end - start))
        self.selected_ids = self.get_initial_process_ids()
        if data_view == "event":
            self.set_biggest_process_ids_for_each_job()
            self.base_case = self.get_dominant_id(self.default_ids).label
        if data_view == "process":
            self.base_case = self.get_dominant_id(self.selected_ids).label
        self.flamegraph_process_ids = [self.get_base_case_id()]
        self.start = self.get_min_x()
        self.stop = self.get_max_x()
        self.text_filter = ""

    def create_tasks(self):
        for result_file in self.results_files:
            full_filename = os.path.join(self.path, result_file)
            job = get_job_name(result_file)
            with open(full_filename) as infile:
                for line in infile:
                    if re.match("event_counter", line):
                        continue
                    elif re.match("time_interval", line):
                        self.time_interval = float(line.partition(":")[2])
                    elif re.match("cpu_id", line):
                        self.cpu = line.strip().partition(":")[2]
                    elif re.match("system_wide", line):
                        self.system_wide = True
                    else:
                        units = self.cpu_definition.get_active_event_units()
                        match = re.match("(.*proc(all|[0-9]+))_(.*)", line.strip())
                        process = match.group(1)
                        raw_event = match.group(3)
                        process_name = re.sub(job + "_", "", process)
                        full_path = os.path.join(self.path, line.strip())
                        event = raw_event_to_event(raw_event, self.cpu_definition)
                        unit = units[event]
                        event_type = get_event_type(event)
                        if unit == "Samples":
                            counter = self.event_counters[job][raw_event]
                        else:  # Hz
                            counter = 1
                        task_id = process + "_" + event
                        if self.data_view == "process":
                            if process == self.process:
                                self.tasks[task_id] = ReadStacksTask(task_id,
                                                                     full_path,
                                                                     job,
                                                                     process_name,
                                                                     event,
                                                                     raw_event,
                                                                     event_type,
                                                                     counter,
                                                                     self.time_interval)
                        if self.data_view == "event":
                            if raw_event == self.event:
                                self.tasks[task_id] = ReadStacksTask(task_id,
                                                                     full_path,
                                                                     job,
                                                                     process_name,
                                                                     event,
                                                                     raw_event,
                                                                     event_type,
                                                                     counter,
                                                                     self.time_interval)

    def data_update_required(self, start, stop):
        if self.start >= 0.0:
            update = False
            update = update or start != self.start
            update = update or stop != self.stop
        else:
            update = True
        return update

    def read_data(self, start=0.0, stop=sys.float_info.max,
                  text_filter="", selected_ids=[], base_case="", initialise=False):
        self.reset_cached_data()
        self.selected_ids = selected_ids
        self.set_base_case(base_case, self.selected_ids)
        if not self.data_update_required(start, stop):
            self.text_filter = re.escape(text_filter)
            self.compute_totals()
            return
        self.text_filter = re.escape(text_filter)
        self.filtered_stacks = {}
        self.filtered_stacks_x = {}
        self.filtered_stacks_y = {}
        self.start = start
        self.stop = stop
        start_time = start
        stop_time = stop
        self.create_tasks()
        run_parallel = self.n_proc > 1 and len(self.tasks) > 1
        if run_parallel:
            pool = mp.Pool(min(self.n_proc, len(self.tasks)))
            arg_list = []
            for task in self.tasks:
                new_task = self.tasks[task]
                arg_list.append((new_task, start_time, stop_time))
            pool.map(multi_run_wrapper, arg_list)
        else:
            for task in self.tasks:
                new_task = self.tasks[task]
                worker(new_task, start_time, stop_time)

        for task in self.tasks:
            new_task = self.tasks[task]
            task_id = new_task.task_id
            filename = new_task.filename
            finished_task = pickle.load(open(filename + ".p", "rb"))
            self.X[task_id] = finished_task.X
            self.Y[task_id] = finished_task.Y
            os.remove(filename + ".p")

        self.compute_totals()

        for task in self.X:
            for pid in self.X[task]:
                for tid in self.X[task][pid]:
                    for x in self.X[task][pid][tid]:
                        self.min_x = min(self.min_x, x)
                        self.max_x = max(self.max_x, x)
        for task in self.Y:
            for pid in self.Y[task]:
                for tid in self.Y[task][pid]:
                    for y in self.Y[task][pid][tid]:
                        self.min_y = min(self.min_y, y)
                        self.max_y = max(self.max_y, y)
        total_count = 0
        for task in self.totals:
            for pid in self.totals[task]:
                for tid in self.totals[task][pid]:
                    if pid != "all" and tid != "all":
                        y = self.totals[task][pid][tid]
                        total_count += y
        if initialise:
            self.initial_count = self.count
        self.set_process_ids()
        self.calculate_thread_percentages()

    def compute_totals(self):
        keyword = re.compile(self.text_filter)
        process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
        self.totals = {}
        self.count = {}
        for task in self.tasks:
            task_id = self.tasks[task].task_id
            job = self.tasks[task].job
            self.totals[task_id] = {}
            self.count[task_id] = {}
            counter = self.tasks[task_id].event_counter
            event_type = self.tasks[task].event_type
            input_file = self.tasks[task].filename + "_compressed"
            fin = open(input_file, 'r')
            for line in fin:
                k = keyword.search(line)
                if k:
                    stack = line.strip()
                    match = re.search(process_id_regex, line)
                    if match:
                        pid = match.group(2)
                        tid = match.group(3)
                        if pid not in self.totals[task_id]:
                            self.totals[task_id][pid] = {}
                            self.count[task_id][pid] = {}
                        if tid not in self.totals[task_id][pid]:
                            self.totals[task_id][pid][tid] = 0.0
                            self.count[task_id][pid][tid] = [0, 0]
                        if event_type == "custom_event_ratio":
                            stack, par, secondary = stack.rpartition(' ')
                        stack, par, primary = stack.rpartition(' ')
                        c0 = int(primary)
                        if event_type == "custom_event_ratio":
                            c1 = int(secondary)
                        else:
                            c1 = c0
                        if self.stack_map:
                            line = job + ";" + stack
                            if line in self.stack_map:
                                self.count[task_id][pid][tid][0] += counter * c0
                                self.count[task_id][pid][tid][1] += counter * c1
                        else:
                            self.count[task_id][pid][tid][0] += counter * c0
                            self.count[task_id][pid][tid][1] += counter * c1
            fin.close()
        for task_id in self.count:
            event_type = self.tasks[task_id].event_type
            for pid in self.count[task_id]:
                for tid in self.count[task_id][pid]:
                    if event_type == "custom_event_ratio":
                        c0 = float(self.count[task_id][pid][tid][0])
                        c1 = float(self.count[task_id][pid][tid][1])
                        if c1 > 0:
                            self.totals[task_id][pid][tid] = c0 / c1
                    else:
                        c0 = float(self.count[task_id][pid][tid][0])
                        self.totals[task_id][pid][tid] = c0

    def get_label_from_ids(self, task_id, pid, tid):
        label = ""
        for process_id in self.ordered_ids:
            if process_id.task_id == task_id:
                if process_id.pid == pid and process_id.tid == tid:
                    label = process_id.label
        return label

    def set_base_case(self, base_case, selected_ids):
        if len(selected_ids) > 0:
            if base_case in [job.label for job in selected_ids]:
                self.base_case = base_case
            else:
                self.base_case = self.get_dominant_id(selected_ids).label
        else:
            self.base_case = ""

    def get_selected_process_ids(self):
        if len(self.selected_ids) == 0:
            return self.selected_ids
        else:
            # Maintain order from ordered_ids
            selected_ids = [job.label for job in self.selected_ids]
            ids = []
            for process_id in self.ordered_ids:
                if process_id.label in selected_ids:
                    ids.append(process_id)
            return ids

    def set_selected_process_ids(self, ids):
        self.selected_ids = ids

    def get_totals(self):
        if self.stack_map:
            self.compute_totals()
        return self.totals

    def set_stack_map(self, stack_map):
        # If set, stack_map contains stack traces to be output, and maps to augmented stack traces
        self.stack_map = stack_map
        self.reset_cached_data()  # Reset events counts

    def get_flamegraph_process_ids(self):
        return self.flamegraph_process_ids

    def set_flamegraph_process_ids(self, ids):
        self.flamegraph_process_ids = ids

    def get_all_jobs(self):
        return self.all_jobs

    def get_all_process_names(self):
        processes = {}
        for task in self.tasks:
            job = self.tasks[task].job
            if job not in processes:
                processes[job] = []
            process = self.tasks[task].process_name
            if process not in processes[job]:
                processes[job].append(process)
        return processes

    def get_all_event_names(self):
        events = []
        for task in self.tasks:
            event = self.tasks[task].event
            if event not in events:
                events.append(event)
        return events

    def get_all_raw_events(self):
        raw_events = []
        for task in self.tasks:
            raw_event = self.tasks[task].raw_event
            if raw_event not in raw_events:
                raw_events.append(raw_event)
        return raw_events

    def get_all_process_ids(self):
        return self.ordered_ids

    def get_dominant_id(self, ids):
        max_percentage = 0.0
        for process_id in ids:
            if self.data_view == "process" and process_id.event_type == "custom_event_ratio":
                continue
            if process_id.total_percentage > max_percentage:
                max_percentage = process_id.total_percentage
                default_id = process_id
        return default_id

    def set_biggest_process_ids_for_each_job(self):
        self.default_ids = []
        ids = {}
        max_percentage = defaultdict(float)
        for process_id in self.ordered_ids:
            job = process_id.job
            pid = process_id.pid
            tid = process_id.tid
            if self.system_wide:  # Pick maximum for a core, summed over threads
                check = pid != "all" and tid == "all"
            else:  # Pick maximum for a thread
                check = tid != "all"
            if check:
                percentage = process_id.total_percentage
                if percentage > max_percentage[job]:
                    max_percentage[job] = percentage
                    ids[job] = process_id
        for job in ids:
            self.default_ids.append(ids[job])

    def get_biggest_process_ids_for_each_job(self):
        if len(self.default_ids) == 0:
            self.set_biggest_process_ids_for_each_job()
            self.base_case = self.get_dominant_id(self.default_ids).label
        return self.default_ids

    def get_base_case_id(self):
        base_id = None
        for process_id in self.ordered_ids:
            if process_id.label == self.base_case:
                base_id = process_id
        return base_id

    def get_initial_process_ids(self):
        process_ids = []
        for process_id in self.ordered_ids:
            pid = process_id.pid
            tid = process_id.tid
            if self.system_wide:  # Monitor cores
                if pid != "all" and tid == "all":  # One id for each core, including all threads on the core
                    process_ids.append(process_id)
            else:  # Monitor application threads
                if tid != "all":  # One id for each thread of the application
                    process_ids.append(process_id)
        if len(process_ids) == 0:  # No thread/core ids selected - add whatever is selected
            for process_id in self.ordered_ids:
                process_ids.append(process_id)
        return process_ids

    def set_process_ids(self):
        vals = [process_id.label for process_id in self.ordered_ids]  # Store previous ids
        for task in self.totals:
            for pid in self.totals[task]:
                for tid in self.totals[task][pid]:
                    label = task + "-pid:" + pid + "-tid:" + tid
                    job = get_job(task)
                    if job not in self.all_jobs:
                        self.all_jobs.append(job)
                    if label not in vals:
                        process_name = self.tasks[task].process_name
                        event_name = self.tasks[task].event
                        raw_event = self.tasks[task].raw_event
                        event_type = self.tasks[task].event_type
                        vals.append(label)
                        self.ordered_ids.append(StackDataID(job, label, task, pid, tid, process_name,
                                                            event_name, raw_event, event_type))
        self.ordered_ids = natural_sort(self.ordered_ids, key=lambda process_id: process_id.label)
        self.all_jobs = natural_sort(self.all_jobs)

    def calculate_thread_percentages(self):
        total_count = [0, 0, 0]
        max_count1 = [0, 0, 0]
        max_count2 = [0, 0, 0]
        for process_id in self.ordered_ids:
            task = process_id.task_id
            pid = process_id.pid
            tid = process_id.tid
            event_type = process_id.event_type
            process_id.count1 = self.initial_count[task][pid][tid][0]
            process_id.count2 = self.initial_count[task][pid][tid][1]
            if pid != "all" and tid != "all":
                max_count1[0] = max(max_count1[0], process_id.count1)
                max_count2[0] = max(max_count2[0], process_id.count2)
                if event_type == "custom_event_ratio":
                    if self.data_view == "event":
                        total_count[0] += process_id.count2
                else:
                    total_count[0] += process_id.count1
            elif pid != "all":
                max_count1[1] = max(max_count1[1], process_id.count1)
                max_count2[1] = max(max_count2[1], process_id.count2)
                if event_type == "custom_event_ratio":
                    if self.data_view == "event":
                        total_count[1] += process_id.count2
                else:
                    total_count[1] += process_id.count1
            else:
                max_count1[2] = max(max_count1[2], process_id.count1)
                max_count2[2] = max(max_count2[2], process_id.count2)
                if event_type == "custom_event_ratio":
                    if self.data_view == "event":
                        total_count[2] += process_id.count2
                else:
                    total_count[2] += process_id.count1
        for process_id in self.ordered_ids:
            pid = process_id.pid
            tid = process_id.tid
            event_type = process_id.event_type
            if pid != "all" and tid != "all":
                if event_type == "custom_event_ratio":
                    process_id.total_percentage = 100.0 * float(process_id.count2) / float(total_count[0])
                    process_id.max_percentage = 100.0 * float(process_id.count2) / float(max_count2[0])
                else:
                    process_id.total_percentage = 100.0 * float(process_id.count1) / float(total_count[0])
                    process_id.max_percentage = 100.0 * float(process_id.count1) / float(max_count1[0])
            elif pid != "all":
                if event_type == "custom_event_ratio":
                    process_id.total_percentage = 100.0 * float(process_id.count2) / float(total_count[1])
                    process_id.max_percentage = 100.0 * float(process_id.count2) / float(max_count2[1])
                else:
                    process_id.total_percentage = 100.0 * float(process_id.count1) / float(total_count[1])
                    process_id.max_percentage = 100.0 * float(process_id.count1) / float(max_count1[1])
            else:
                if event_type == "custom_event_ratio":
                    process_id.total_percentage = 100.0 * float(process_id.count2) / float(total_count[2])
                    process_id.max_percentage = 100.0 * float(process_id.count2) / float(max_count2[2])
                else:
                    process_id.total_percentage = 100.0 * float(process_id.count1) / float(total_count[2])
                    process_id.max_percentage = 100.0 * float(process_id.count1) / float(max_count1[2])

    def get_system_wide_mode_enabled(self):
        return self.system_wide

    def get_collapsed_stacks_filename(self):
        return self.collapsed_stacks_filename

    def get_min_x(self):
        return self.min_x

    def get_max_x(self):
        return self.max_x

    def get_min_y(self):
        return self.min_y

    def get_max_y(self):
        return self.max_y

    def get_step_x(self):
        return self.time_interval

    def get_step_y(self):
        return (self.max_y - self.min_y) / 20.0

    def reset_cached_data(self):
        self.filtered_stacks_x = {}
        self.filtered_stacks_y = {}
        self.filtered_stacks = {}

    def get_custom_event_ratio_stack_data(self, process_id):
        keyword = re.compile(self.text_filter)
        process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
        task_id = process_id.task_id
        job = process_id.job
        counter = float(self.tasks[task_id].event_counter)
        pid = process_id.pid
        tid = process_id.tid
        if task_id in self.filtered_stacks_x:
            if pid in self.filtered_stacks_x[task_id]:
                if tid in self.filtered_stacks_x[task_id][pid]:  # Return cached data
                    return self.filtered_stacks_x[task_id][pid][tid], self.filtered_stacks_y[task_id][pid][tid]
        else:
            self.filtered_stacks_x[task_id] = {}
            self.filtered_stacks_y[task_id] = {}
        input_file = self.tasks[task_id].filename + "_compressed"
        fin = open(input_file, 'r')
        for line in fin:
            k = keyword.search(line)
            if k:
                match = re.search(process_id_regex, line)
                if match:
                    pid = match.group(2)
                    tid = match.group(3)
                    if pid not in self.filtered_stacks_x[task_id]:
                        self.filtered_stacks_x[task_id][pid] = {}
                        self.filtered_stacks_y[task_id][pid] = {}
                    if tid not in self.filtered_stacks_x[task_id][pid]:
                        self.filtered_stacks_x[task_id][pid][tid] = {}
                        self.filtered_stacks_y[task_id][pid][tid] = {}
                    stack, par, count2 = line.rpartition(" ")
                    stack, par, count1 = stack.rpartition(" ")
                    s = job + ";" + stack
                    if self.stack_map:
                        line = job + ";" + stack
                        if line in self.stack_map:
                            self.filtered_stacks_x[task_id][pid][tid][s] = counter * float(count2)
                            self.filtered_stacks_y[task_id][pid][tid][s] = counter * float(count1)
                    else:
                        self.filtered_stacks_x[task_id][pid][tid][s] = counter * float(count2)
                        self.filtered_stacks_y[task_id][pid][tid][s] = counter * float(count1)
        fin.close()
        pid = process_id.pid
        tid = process_id.tid
        # Return empty container if no match found
        if pid not in self.filtered_stacks_x[task_id]:
            self.filtered_stacks_x[task_id][pid] = {}
            self.filtered_stacks_y[task_id][pid] = {}
        if tid not in self.filtered_stacks_x[task_id][pid]:
            self.filtered_stacks_x[task_id][pid][tid] = {}
            self.filtered_stacks_y[task_id][pid][tid] = {}
        return self.filtered_stacks_x[task_id][pid][tid], self.filtered_stacks_y[task_id][pid][tid]

    def get_original_event_stack_data(self, process_id):
        keyword = re.compile(self.text_filter)
        process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
        task_id = process_id.task_id
        job = process_id.job
        counter = float(self.tasks[task_id].event_counter)
        pid = process_id.pid
        tid = process_id.tid
        if task_id in self.filtered_stacks:
            if pid in self.filtered_stacks[task_id]:
                if tid in self.filtered_stacks[task_id][pid]:  # Return cached data
                    return self.filtered_stacks[task_id][pid][tid]
        else:
            self.filtered_stacks[task_id] = {}
        input_file = self.tasks[task_id].filename + "_compressed"
        fin = open(input_file, 'r')
        for line in fin:
            k = keyword.search(line)
            if k:
                match = re.search(process_id_regex, line)
                if match:
                    pid = match.group(2)
                    tid = match.group(3)
                    if pid not in self.filtered_stacks[task_id]:
                        self.filtered_stacks[task_id][pid] = {}
                    if tid not in self.filtered_stacks[task_id][pid]:
                        self.filtered_stacks[task_id][pid][tid] = {}
                    stack, par, count1 = line.rpartition(" ")
                    s = job + ";" + stack
                    if self.stack_map:
                        line = job + ";" + stack
                        if line in self.stack_map:
                            self.filtered_stacks[task_id][pid][tid][s] = counter * float(count1)
                    else:
                        self.filtered_stacks[task_id][pid][tid][s] = counter * float(count1)
        fin.close()
        pid = process_id.pid
        tid = process_id.tid
        # Return empty container if no match found
        if pid not in self.filtered_stacks[task_id]:
            self.filtered_stacks[task_id][pid] = {}
        if tid not in self.filtered_stacks[task_id][pid]:
            self.filtered_stacks[task_id][pid][tid] = {}
        return self.filtered_stacks[task_id][pid][tid]


def write_flamegraph_stacks(stack_data, flamegraph_type, append=False, output_event_type="original"):
    keyword = re.compile(stack_data.text_filter)
    process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
    if flamegraph_type == "diff_symbols":
        data = OrderedDict()
        base_symbols = {}
        symbols = {}
        base_case_id = stack_data.get_base_case_id()
        base_task_id = base_case_id.task_id
        base_pid = base_case_id.pid
        base_tid = base_case_id.tid
        ids = stack_data.get_flamegraph_process_ids()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            if task_id == base_task_id:
                input_file = stack_data.tasks[task].filename + "_compressed"
                fin = open(input_file, 'r')
                for line in fin:
                    k = keyword.search(line)
                    if k:
                        match = re.search(process_id_regex, line)
                        if match:
                            p = match.group(2)
                            t = match.group(3)
                            if p == base_pid and t == base_tid:
                                stack, par, count = line.strip().rpartition(" ")
                                symbol = stack.rpartition(";")[2]
                                c = int(count)
                                if symbol in base_symbols:
                                    c += int(base_symbols[symbol])
                                base_symbols[symbol] = str(c)
                fin.close()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            pids = []
            for process_id in ids:
                if process_id.task_id == task_id:
                    pids.append((process_id.pid, process_id.tid))
            if len(pids) > 0:
                input_file = stack_data.tasks[task].filename + "_compressed"
                fin = open(input_file, 'r')
                for line in fin:
                    k = keyword.search(line)
                    if k:
                        match = re.search(process_id_regex, line)
                        if match:
                            p = match.group(2)
                            t = match.group(3)
                            if (p, t) in pids:
                                label = stack_data.get_label_from_ids(task_id, p, t)
                                if label not in data:
                                    data[label] = OrderedDict()
                                    symbols[label] = {}
                                stack, par, count = line.strip().rpartition(" ")
                                symbol = stack.rpartition(";")[2]
                                c = int(count)
                                if symbol in symbols[label]:
                                    c += int(symbols[label][symbol])
                                symbols[label][symbol] = str(c)
                                data[label][stack] = count
                fin.close()
        output_file = os.path.join(stack_data.path, stack_data.collapsed_stacks_filename)
        if append:
            f = open(output_file, 'ab')
        else:
            f = open(output_file, 'wb')
        for label in data:
            for stack in data[label]:
                symbol = stack.rpartition(";")[2]
                count = int(data[label][stack])
                base_count = 0
                if symbol in base_symbols:
                    r = float(base_symbols[symbol]) / float(symbols[label][symbol])
                    base_count = int(r * float(count))
                job = get_job(label)
                ll = job + ";" + stack + " " + str(base_count) + " " + str(count) + "\n"
                f.write(ll.encode())
        f.close()
    elif flamegraph_type == "diff_stack_traces":
        base_data = OrderedDict()
        data = OrderedDict()
        base_case_id = stack_data.get_base_case_id()
        base_task_id = base_case_id.task_id
        base_pid = base_case_id.pid
        base_tid = base_case_id.tid
        ids = stack_data.get_flamegraph_process_ids()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            if task_id == base_task_id:
                input_file = stack_data.tasks[task].filename + "_compressed"
                fin = open(input_file, 'r')
                for line in fin:
                    k = keyword.search(line)
                    if k:
                        match = re.search(process_id_regex, line)
                        if match:
                            p = match.group(2)
                            t = match.group(3)
                            if p == base_pid and t == base_tid:
                                stack, par, count = line.strip().rpartition(" ")
                                s = re.sub("((\-all|[\-0-9]+)/(all|[0-9]+))", "", stack)
                                base_data[s] = count
                fin.close()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            pids = []
            for process_id in ids:
                if process_id.task_id == task_id:
                    pids.append((process_id.pid, process_id.tid))
            if len(pids) > 0:
                data[task_id] = OrderedDict()
                input_file = stack_data.tasks[task].filename + "_compressed"
                fin = open(input_file, 'r')
                for line in fin:
                    k = keyword.search(line)
                    if k:
                        match = re.search(process_id_regex, line)
                        if match:
                            p = match.group(2)
                            t = match.group(3)
                            if (p, t) in pids:
                                label = stack_data.get_label_from_ids(task_id, p, t)
                                if label not in data:
                                    data[label] = OrderedDict()
                                stack, par, count = line.strip().rpartition(" ")
                                data[label][stack] = count
                fin.close()
        output_file = os.path.join(stack_data.path, stack_data.collapsed_stacks_filename)
        if append:
            f = open(output_file, 'ab')
        else:
            f = open(output_file, 'wb')
        for label in data:
            for stack in data[label]:
                s = re.sub("((\-all|[\-0-9]+)/(all|[0-9]+))", "", stack)
                base_count = 0
                count = data[label][stack]
                if s in base_data:
                    base_count = base_data[s]
                job = get_job(label)
                ll = job + ";" + stack + " " + str(base_count) + " " + str(count) + "\n"
                f.write(ll.encode())
        f.close()
    elif flamegraph_type == "plot_for_process":
        output_file = os.path.join(stack_data.path, stack_data.collapsed_stacks_filename)
        if append:
            f = open(output_file, 'ab')
        else:
            f = open(output_file, 'wb')
        ids = stack_data.get_flamegraph_process_ids()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            event_type = stack_data.tasks[task].event_type
            job = stack_data.tasks[task].job
            pids = []
            for process_id in ids:
                if process_id.task_id == task_id:
                    pids.append((process_id.pid, process_id.tid))
            if len(pids) > 0:
                if event_type == output_event_type:
                    input_file = stack_data.tasks[task].filename + "_compressed"
                    fin = open(input_file, 'r')
                    for line in fin:
                        k = keyword.search(line)
                        if k:
                            match = re.search(process_id_regex, line)
                            if match:
                                p = match.group(2)
                                t = match.group(3)
                                if (p, t) in pids:
                                    if event_type == "custom_event_ratio":
                                        ll = task_id + ";" + line
                                        f.write(ll.encode())
                                    else:
                                        if stack_data.stack_map:
                                            stack, par, count1 = line.rpartition(" ")
                                            line = job + ";" + stack
                                            if line in stack_data.stack_map:
                                                ll = task_id + ";" + stack_data.stack_map[line] + " " + count1
                                                f.write(ll.encode())
                                        else:
                                            ll = task_id + ";" + line
                                            f.write(ll.encode())
                    fin.close()
        f.close()
    elif flamegraph_type == "plot_for_event":
        output_file = os.path.join(stack_data.path, stack_data.collapsed_stacks_filename)
        if append:
            f = open(output_file, 'ab')
        else:
            f = open(output_file, 'wb')
        ids = stack_data.get_flamegraph_process_ids()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            pids = []
            for process_id in ids:
                if process_id.task_id == task_id:
                    pids.append((process_id.pid, process_id.tid))
            if len(pids) > 0:
                input_file = stack_data.tasks[task].filename + "_compressed"
                fin = open(input_file, 'r')
                for line in fin:
                    k = keyword.search(line)
                    if k:
                        match = re.search(process_id_regex, line)
                        if match:
                            p = match.group(2)
                            t = match.group(3)
                            if (p, t) in pids:
                                ll = task_id + ";" + line
                                f.write(ll.encode())
                fin.close()
        f.close()
