import re
import os
import sys
from collections import OrderedDict
from timeit import default_timer as timer
from tools.ResultsHandler import get_job_name, get_event_counters
from tools.CustomEvents import raw_event_to_event
from tools.Utilities import natural_sort, is_float
import operator


def get_job(task_or_label):
    """Get job from task_id or label, where
    task_id = job_processor_event, and
    label = task_id + "-pid:" + pid + "-tid:" + tid"""
    job = re.sub("_proc[0-9]+_.*", "", task_or_label)
    job = re.sub("_procall_.*", "", job)
    job = re.sub("_host[0-9]+", "", job)
    return job


def get_pid(task_or_label):
    """Get pid from task_id or label, where
    task_id = job_processor_event, and
    label = task_id + "-pid:" + pid + "-tid:" + tid"""
    pid = task_or_label.rpartition("-pid:")[2].rpartition("-tid:")[0]
    return pid


def get_tid(task_or_label):
    """Get pid from task_id or label, where
    task_id = job_processor_event, and
    label = task_id + "-pid:" + pid + "-tid:" + tid"""
    tid = task_or_label.rpartition("-tid:")[2]
    return tid


class TraceDataID:
    """Metadata for collapsed stacks trace data for a specific job, event, process, and thread."""

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


class ReadTraceTask:

    def __init__(self, task_id, filename, job, process_name, event, raw_event,
                 event_type, counter, time_scale, sample_weight):
        self.task_id = task_id
        self.filename = filename
        self.job = job
        self.process_name = process_name
        self.event = event
        self.raw_event = raw_event
        self.event_type = event_type
        self.event_counter = counter
        self.time_scale = time_scale
        self.sample_weight = sample_weight
        self.trace_data = {}
        self.start_time = -1.0
        self.totals = {}
        self.timelines = {}
        self.sample_rates = {}
        self.secondary_event_samples = {}
        self.ordered_nodes = []
        self.time_norm = 0.0
        self.previous_stacks = {}
        self.previous_context = {}
        self.call_counts = {}

    def get_start_time(self):
        if self.start_time > 0.0:
            return self.start_time
        file = self.filename
        with open(file) as infile:
            first_line = infile.readline()
        self.start_time = float(first_line.strip().rpartition(';')[2])
        return self.start_time

    def execute(self, offset=0.0):
        file = self.filename
        process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
        with open(file) as infile:
            for line in infile:
                line = line.strip()
                match = re.search(process_id_regex, line)
                if match:
                    pid = match.group(2)
                    tid = match.group(3)
                    match2 = re.match("secondary-event;([^:]+):(.*):\s*(.*)", line)
                    if match2:
                        event = match2.group(2)
                        samples = match2.group(3)
                        samples = samples.split(" ")
                        if pid not in self.secondary_event_samples:
                            self.secondary_event_samples[pid] = {}
                        if tid not in self.secondary_event_samples[pid]:
                            self.secondary_event_samples[pid][tid] = {}
                        if event not in self.secondary_event_samples[pid][tid]:
                            self.secondary_event_samples[pid][tid][event] = []
                        for sample in samples:
                            self.secondary_event_samples[pid][tid][event].append(float(sample) + offset)
                        continue
                    this_id = pid + "-" + tid
                    stack = line
                    data = stack.split(" ")
                    samples = [float(x) + offset for x in data[1:] if is_float(x)]
                    n = len(data)
                    m = len(samples)
                    stack = " ".join(data[0:n - m])
                    frames = stack.split(";")
                    if len(frames) == 1:
                        frames.append("-")  # No context information
                    this_context = this_id + frames[1]
                    if this_context not in self.previous_context:
                        self.previous_context[this_context] = ""
                        self.call_counts[this_context] = {}
                    previous_stack = self.previous_context[this_context]
                    self.unwind_stacks(this_context, frames, previous_stack)
                    self.previous_context[this_context] = stack
                    new_stack = frames[0:2]
                    for i in range(2, len(frames)):
                        new_stack.append(frames[i] + "_[[call_" + str(self.call_counts[this_context][frames[i]]) + "]]")
                    stack = ";".join(new_stack)
                    entry_time = samples[0]
                    exit_time = samples[-1]
                    if pid not in self.trace_data:
                        self.trace_data[pid] = {}
                        self.totals[pid] = {}
                    if tid not in self.trace_data[pid]:
                        self.trace_data[pid][tid] = []
                        self.trace_data[pid][tid].append([])
                        self.totals[pid][tid] = 0.0
                    time_index = int(entry_time)
                    last_time = len(self.trace_data[pid][tid]) - 1
                    if time_index > last_time:
                        for t in range(last_time + 1, time_index + 1):
                            self.trace_data[pid][tid].append([])
                    trace = {"stack": stack, "samples": samples}
                    self.trace_data[pid][tid][time_index].append(trace)
                    self.totals[pid][tid] += self.time_scale * (exit_time - entry_time + self.sample_weight)
                    self.time_norm = max(self.time_norm, exit_time)

    def unwind_stacks(self, this_context, frames, previous_stack):
        test_stack = ""
        for frame in frames:
            test_stack += frame
            if not (previous_stack.startswith(test_stack + ";") or previous_stack == test_stack):
                if frame not in self.call_counts[this_context]:
                    self.call_counts[this_context][frame] = 1
                else:
                    self.call_counts[this_context][frame] += 1
            test_stack += ";"

    def get_time_norm(self):
        return self.time_norm


class TraceData:

    def __init__(self, results_files, path, cpu_definition, data_id="", debug=True):
        self.selected_ids = []
        self.all_jobs = []
        self.all_tasks = []
        self.initial_count = 0
        self.time_norm = 1.0
        self.timeline_start = -0.0000001
        self.timeline_end = sys.maxsize
        self.timeline_dt = 1.0
        self.cpu_definition = cpu_definition
        self.results_files = results_files
        self.stack_file = ""
        self.event_counters = {}
        self.path = path
        self.system_wide = False
        self.job = data_id
        self.time_interval = 0.0
        self.timeline_intervals = 200
        self.time_scale = 1000000.0
        self.cpu = ""
        self.tasks = OrderedDict()
        self.trace_event_type = "counter"
        self.sample_weight = 1.0
        self.event_counters = get_event_counters(path, results_files)
        self.collapsed_stacks_filename = "data_stacks_collapsed"
        self.timelines_filename = "trace_timeline"
        self.event = "trace"
        self.ordered_ids = []
        self.default_ids = []
        self.hotspots = {}
        self.augmented_hotspots = {}
        self.totals = {}
        self.timelines = {}
        self.start_times = {}
        self.time_offsets = {}
        self.secondary_events = {}
        self.secondary_event_samples = {}
        self.sample_rates = {}
        self.trace_data = {}
        self.ordered_nodes = {}

        self.debug = debug
        if debug:
            start = timer()
        self.read_data(initialise=True)  # Read all data on the first pass
        if debug:
            end = timer()
            print("Time to load data: " + str(end - start))
        self.selected_ids = self.get_initial_process_ids()
        self.base_case = self.selected_ids[0].label
        self.flamegraph_process_ids = [self.get_base_case_id()]

    def create_tasks(self):
        for result_file in self.results_files:
            full_filename = os.path.join(self.path, result_file)
            job = get_job_name(result_file)
            if self.job != job:
                continue
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
                        process, par, raw_event = line.strip().rpartition('_')
                        if re.search("trace", raw_event):
                            process_name = re.sub(job + "_", "", process)
                            full_path = os.path.join(self.path, line.strip())
                            event = raw_event_to_event(raw_event, self.cpu_definition)
                            counter = self.event_counters[job][raw_event]
                            event_type = "trace"
                            if re.match("clock", raw_event):
                                self.trace_event_type = "clock"
                                self.sample_weight = 1.0 / float(counter)  # Convert from Hz to seconds
                            else:
                                self.trace_event_type = "counter"
                                self.sample_weight = 1.0
                            task_id = process + "_" + event
                            self.tasks[task_id] = ReadTraceTask(task_id,
                                                                full_path,
                                                                job,
                                                                process_name,
                                                                event,
                                                                raw_event,
                                                                event_type,
                                                                counter,
                                                                self.time_scale,
                                                                self.sample_weight)

    def read_data(self, start=-0.0000001, stop=sys.float_info.max, selected_ids=[], initialise=False):
        start = start
        stop = stop
        if initialise:
            self.time_norm = 0.0
            self.create_tasks()
            min_time = sys.maxsize
            for task_id in self.tasks:
                time = self.tasks[task_id].get_start_time()
                min_time = min(min_time, time)
            for task_id in self.tasks:
                time = self.tasks[task_id].get_start_time()
                offset = time - min_time
                self.tasks[task_id].execute(offset)
                self.totals[task_id] = self.tasks[task_id].totals
                self.start_times[task_id] = self.tasks[task_id].start_time
                self.trace_data[task_id] = self.tasks[task_id].trace_data
                self.secondary_event_samples[task_id] = self.tasks[task_id].secondary_event_samples
                self.time_norm = max(self.time_norm, self.tasks[task_id].get_time_norm())
            self.set_time_offsets()
            self.initial_count = self.totals
            self.set_process_ids()
            self.calculate_thread_percentages()
        self.selected_ids = selected_ids
        if initialise:
            self.compute_hotspots()
            self.reset_hotspots()
            self.create_augmented_hotspots(start, stop)

    def set_time_offsets(self):
        min_time = sys.maxsize
        for task_id in self.tasks:
            min_time = min(self.tasks[task_id].start_time, min_time)
        for task_id in self.tasks:
            self.time_offsets[task_id] = self.tasks[task_id].start_time - min_time

    def set_process_ids(self):
        vals = [process_id.label for process_id in self.ordered_ids]  # Store previous ids
        for task_id in self.totals:
            for pid in self.totals[task_id]:
                for tid in self.totals[task_id][pid]:
                    label = task_id + "-pid:" + pid + "-tid:" + tid
                    job = get_job(task_id)
                    if job not in self.all_jobs:
                        self.all_jobs.append(job)
                    if label not in vals:
                        process_name = self.tasks[task_id].process_name
                        event_name = self.tasks[task_id].event
                        raw_event = self.tasks[task_id].raw_event
                        event_type = self.tasks[task_id].event_type
                        vals.append(label)
                        self.ordered_ids.append(TraceDataID(job, label, task_id, pid, tid, process_name,
                                                            event_name, raw_event, event_type))
        self.ordered_ids = natural_sort(self.ordered_ids, key=lambda process_id: process_id.label)
        self.all_jobs = natural_sort(self.all_jobs)

    def calculate_thread_percentages(self):
        total_count = [0, 0, 0]
        max_count = [0, 0, 0]
        for id in self.ordered_ids:
            task = id.task_id
            pid = id.pid
            tid = id.tid
            id.count1 = self.initial_count[task][pid][tid]
            if pid != "all" and tid != "all":
                max_count[0] = max(max_count[0], id.count1)
                total_count[0] += id.count1
            elif pid != "all":
                max_count[1] = max(max_count[1], id.count1)
                total_count[1] += id.count1
            else:
                max_count[2] = max(max_count[2], id.count1)
                total_count[2] += id.count1
        for id in self.ordered_ids:
            pid = id.pid
            tid = id.tid
            if pid != "all" and tid != "all":
                id.total_percentage = 100.0 * float(id.count1) / float(total_count[0])
                id.max_percentage = 100.0 * float(id.count1) / float(max_count[0])
            elif pid != "all":
                id.total_percentage = 100.0 * float(id.count1) / float(total_count[1])
                id.max_percentage = 100.0 * float(id.count1) / float(max_count[1])
            else:
                id.total_percentage = 100.0 * float(id.count1) / float(total_count[2])
                id.max_percentage = 100.0 * float(id.count1) / float(max_count[2])

    def generate_timelines(self, t1=-0.0000001, t2=sys.maxsize):
        if t1 >= 0.0 and t2 < sys.maxsize:
            dt = (t2 - t1) / float(self.timeline_intervals)
            self.timeline_start = t1
            self.timeline_end = t2
            self.timeline_dt = dt
        else:
            dt = self.time_norm / float(self.timeline_intervals)
            self.timeline_start = 0
            self.timeline_end = self.time_norm
            self.timeline_dt = dt
        self.timelines = {}
        for task_id in self.trace_data:
            self.timelines[task_id] = {}
            for pid in self.trace_data[task_id]:
                if pid not in self.timelines[task_id]:
                    self.timelines[task_id][pid] = {}
                for tid in self.trace_data[task_id][pid]:
                    if tid not in self.timelines[task_id][pid]:
                        self.timelines[task_id][pid][tid] = ["no_samples"] * self.timeline_intervals
                    max_node = [-1.0 for i in range(self.timeline_intervals)]
                    for time_slice in self.trace_data[task_id][pid][tid]:
                        for time_slice_interval in time_slice:
                            trace = time_slice_interval["stack"]
                            start = time_slice_interval["samples"][0]
                            end = time_slice_interval["samples"][-1]
                            if end > t1 and start <= t2:
                                i_begin = int(max(0, start - t1) / dt)
                                i_end = int(min(t2 - t1, end - t1) / dt)
                                for i in range(i_begin, i_end + 1):
                                    x1 = max(t1 + i * dt, start)
                                    x2 = min(t1 + (i + 1) * dt, end)
                                    index = min(i, self.timeline_intervals - 1)
                                    if x2 - x1 > max_node[index]:
                                        max_node[index] = x2 - x1
                                        node = trace.rpartition(";")[2]
                                        self.timelines[task_id][pid][tid][index] = node
        self.generate_sample_rates(t1, t2)
        self.generate_secondary_events(t1, t2)

    def get_next_call(self, t1, t2, pid, tid, function_name, n, forwards=True):
        if forwards:
            m = n + 1
            p = n + 2
        else:
            m = n - 1
            p = n
        t1_out = sys.maxsize
        t2_out = -sys.maxsize
        f_out = function_name + "_[[call_" + str(m) + "]]"
        found = False
        function_regex = re.compile(function_name + "_\[\[call_" + str(m) + "\]\]")
        exit_regex = re.compile(function_name + "_\[\[call_" + str(p) + "\]\]")
        for id in self.selected_ids:
            if id.pid == pid and id.tid == tid:
                task_id = id.task_id
                for time_index, time_slice in enumerate(self.trace_data[task_id][pid][tid]):
                    if forwards and time_index >= int(t1) or not forwards and time_index <= int(t2):
                        for i in range(0, len(time_slice)):
                            trace = time_slice[i]["stack"]
                            start = time_slice[i]["samples"][0]
                            end = time_slice[i]["samples"][-1]
                            match = re.search(function_regex, trace)
                            if match:
                                t1_out = min(t1_out, start)
                                t2_out = max(t2_out, end)
                                found = True
                            if found:
                                exit_search = re.search(exit_regex, trace)
                                if exit_search:
                                    if t2_out - t1_out < 0.0000001:  # Single sample
                                        t2_out = start
                                        t1_out = t1_out - 0.0000001
                                    return f_out, t1_out, t2_out
        if not found:
            t1_out = t1
            t2_out = t2
            f_out = function_name
        return f_out, t1_out, t2_out

    def generate_sample_rates(self, t1=-0.0000001, t2=sys.maxsize):
        dt = self.timeline_dt
        self.sample_rates = {}
        for task_id in self.trace_data:
            self.sample_rates[task_id] = {}
            for pid in self.trace_data[task_id]:
                if pid not in self.sample_rates[task_id]:
                    self.sample_rates[task_id][pid] = {}
                for tid in self.trace_data[task_id][pid]:
                    if tid not in self.sample_rates[task_id][pid]:
                        self.sample_rates[task_id][pid][tid] = [0.0] * self.timeline_intervals
                    for time_slice in self.trace_data[task_id][pid][tid]:
                        for i in range(len(time_slice)):
                            for time in time_slice[i]["samples"]:
                                if t1 <= time <= t2:
                                    index = min(int((time - t1) / dt), self.timeline_intervals - 1)
                                    self.sample_rates[task_id][pid][tid][index] += 1.0
        for task_id in self.sample_rates:
            for pid in self.sample_rates[task_id]:
                for tid in self.sample_rates[task_id][pid]:
                    for index in range(len(self.sample_rates[task_id][pid][tid])):
                        self.sample_rates[task_id][pid][tid][index] /= dt

    def generate_secondary_events(self, t1=-0.0000001, t2=sys.maxsize):
        if t1 <= 0.0 and t2 == sys.maxsize:
            self.secondary_events = self.secondary_event_samples
            return
        self.secondary_events = {}
        for task_id in self.secondary_event_samples:
            self.secondary_events[task_id] = {}
            for pid in self.secondary_event_samples[task_id]:
                if pid not in self.secondary_events[task_id]:
                    self.secondary_events[task_id][pid] = {}
                for tid in self.secondary_event_samples[task_id][pid]:
                    if tid not in self.secondary_events[task_id][pid]:
                        self.secondary_events[task_id][pid][tid] = {}
                        for event in self.secondary_event_samples[task_id][pid][tid]:
                            if event not in self.secondary_events[task_id][pid][tid]:
                                self.secondary_events[task_id][pid][tid][event] = []
                            for time in self.secondary_event_samples[task_id][pid][tid][event]:
                                if t1 <= time <= t2:
                                    self.secondary_events[task_id][pid][tid][event].append(time)

    def compute_hotspots(self):
        nodes = OrderedDict()
        for task_id in self.tasks:
            sample_weight = self.tasks[task_id].sample_weight
            for pid in self.trace_data[task_id]:
                for tid in self.trace_data[task_id][pid]:
                    for time_slice in self.trace_data[task_id][pid][tid]:
                        for i in range(len(time_slice)):
                            trace = time_slice[i]["stack"]
                            start = time_slice[i]["samples"][0]
                            end = time_slice[i]["samples"][-1]
                            augmented_node = trace.rpartition(";")[2]
                            node = re.sub("_\[\[call_[0-9]+\]\]", "", augmented_node)
                            if node not in nodes:
                                nodes[node] = 0.0
                            nodes[node] += self.time_scale * (end - start + sample_weight)
        self.ordered_nodes = sorted(nodes.items(), key=operator.itemgetter(1), reverse=True)

    def get_flamegraph_process_ids(self):
        return self.flamegraph_process_ids

    def set_flamegraph_process_ids(self, ids):
        self.flamegraph_process_ids = ids

    def get_all_jobs(self):
        return self.all_jobs

    def get_all_process_ids(self):
        return self.ordered_ids

    def get_system_wide_mode_enabled(self):
        return self.system_wide

    def get_collapsed_stacks_filename(self):
        return self.collapsed_stacks_filename

    def get_timelines_filename(self):
        return self.timelines_filename

    def get_num_timeline_intervals(self):
        return self.timeline_intervals

    def get_base_case_id(self):
        base_id = None
        for process_id in self.ordered_ids:
            if process_id.label == self.base_case:
                base_id = process_id
        return base_id

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
        return process_ids

    def get_trace_event_type(self):
        return self.trace_event_type

    def reset_hotspots(self, n=10):
        self.hotspots = {}
        count = 0
        for node in self.ordered_nodes:
            self.hotspots[node[0]] = count
            count += 1
            if count == n:
                break

    def get_hotspots(self, augmented=False):
        if augmented:
            return self.augmented_hotspots
        else:
            return self.hotspots

    def set_hotspots(self, hotspots, augmented=False):
        if augmented:
            self.augmented_hotspots = hotspots
        else:
            self.hotspots = hotspots

    def create_augmented_hotspots(self, t1, t2):
        hotspots = self.get_hotspots()
        augmented_hotspots = {}
        ids = self.get_all_process_ids()
        for task_id in self.tasks:
            pids = []
            for id in ids:
                if id.task_id == task_id:
                    pids.append((id.pid, id.tid))
            for pid, tid in pids:
                for time_index, time_slice in enumerate(self.trace_data[task_id][pid][tid]):
                    if int(t1) <= time_index <= int(t2) and len(time_slice) > 0:
                        for i in range(len(time_slice)):
                            trace = time_slice[i]["stack"]
                            start = time_slice[i]["samples"][0]
                            end = time_slice[i]["samples"][-1]
                            if end > t1 and start <= t2:
                                augmented_node = trace.rpartition(";")[2]
                                node = re.sub("_\[\[call_[0-9]+\]\]", "", augmented_node)
                                if node in hotspots:
                                    augmented_hotspots[augmented_node] = hotspots[node]
        self.set_hotspots(augmented_hotspots, augmented=True)


def write_flamegraph_stacks(stack_data, flamegraph_type, t1=-0.0000001, t2=sys.maxsize):
    output_file = os.path.join(stack_data.path, stack_data.collapsed_stacks_filename)
    time_scale = stack_data.time_scale
    if flamegraph_type == "cumulative":
        collapsed_stacks = {}
        ids = stack_data.get_flamegraph_process_ids()
        for task_id in stack_data.tasks:
            sample_weight = stack_data.tasks[task_id].sample_weight
            pids = []
            for id in ids:
                if id.task_id == task_id:
                    pids.append((id.pid, id.tid))
            for pid, tid in pids:
                previous_x2 = t1
                if pid not in collapsed_stacks:
                    collapsed_stacks[pid] = {}
                if tid not in collapsed_stacks[pid]:
                    collapsed_stacks[pid][tid] = {}
                for time_index, time_slice in enumerate(stack_data.trace_data[task_id][pid][tid]):
                    if int(t1) <= time_index <= int(t2):
                        for i in range(len(time_slice)):
                            trace = time_slice[i]["stack"]
                            new_trace = re.sub("_\[\[call_[0-9]+\]\]", "", trace)
                            start = time_slice[i]["samples"][0]
                            end = time_slice[i]["samples"][-1]
                            if end > t1 and start <= t2:
                                x1 = max(start, t1)
                                x2 = min(end, t2)
                                if x1 - previous_x2 > 1.25 * sample_weight:  # Ignore random noise
                                    elapsed_delta = time_scale * (x1 - previous_x2 - sample_weight)
                                    no_samples = "no_samples"
                                    if no_samples not in collapsed_stacks[pid][tid]:
                                        collapsed_stacks[pid][tid][no_samples] = 0
                                    collapsed_stacks[pid][tid][no_samples] += elapsed_delta
                                if new_trace not in collapsed_stacks[pid][tid]:
                                    collapsed_stacks[pid][tid][new_trace] = 0
                                collapsed_stacks[pid][tid][new_trace] += time_scale * (x2 - x1 + sample_weight)
                                previous_x2 = x2
                # Fill in space for final interval between samples
                if t2 < sys.maxsize:
                    if t2 - previous_x2 > 1.25 * sample_weight:  # Ignore random noise
                        elapsed_delta = time_scale * (t2 - previous_x2 - sample_weight)
                        no_samples = "no_samples"
                        if no_samples not in collapsed_stacks[pid][tid]:
                            collapsed_stacks[pid][tid][no_samples] = 0
                        collapsed_stacks[pid][tid][no_samples] += elapsed_delta
        f = open(output_file, 'wb')
        for pid in collapsed_stacks:
            for tid in collapsed_stacks[pid]:
                for trace in collapsed_stacks[pid][tid]:
                    total = collapsed_stacks[pid][tid][trace]
                    n = int(total)
                    if n > 0:
                        out = trace + " " + str(int(total)) + "\n"
                        f.write(out.encode())
        f.close()
    elif flamegraph_type == "trace":
        max_lines = 2000
        line_num = 0
        f = open(output_file, 'wb')
        ids = stack_data.get_flamegraph_process_ids()
        for task_id in stack_data.tasks:
            sample_weight = stack_data.tasks[task_id].sample_weight
            pids = []
            for id in ids:
                if id.task_id == task_id:
                    pids.append((id.pid, id.tid))
            for pid, tid in pids:
                previous_x2 = t1
                for time_index, time_slice in enumerate(stack_data.trace_data[task_id][pid][tid]):
                    if int(t1) <= time_index <= int(t2) and len(time_slice) > 0:
                        for i in range(len(time_slice)):
                            trace = time_slice[i]["stack"]
                            start = time_slice[i]["samples"][0]
                            end = time_slice[i]["samples"][-1]
                            if end > t1 and start <= t2:
                                x1 = max(start, t1)
                                x2 = min(end, t2)
                                # Fill in space for interval between samples
                                if x1 - previous_x2 > 1.25 * sample_weight:  # Ignore random noise
                                    elapsed_delta = time_scale * (x1 - previous_x2 - sample_weight)
                                    n = int(elapsed_delta)
                                    if n > 0:
                                        out = "no_samples " + str(n) + "\n"
                                        f.write(out.encode())
                                        line_num += 1
                                delta = time_scale * (x2 - x1 + sample_weight)  # milliseconds
                                n = int(delta)
                                if n > 0:
                                    out = trace + " " + str(n) + "\n"
                                    f.write(out.encode())
                                    line_num += 1
                                    if line_num > max_lines:
                                        f.close()
                                        return
                                previous_x2 = x2
                # Fill in space for final interval between samples
                if t2 < sys.maxsize:
                    if t2 - previous_x2 > 1.25 * sample_weight:  # Ignore random noise
                        elapsed_delta = time_scale * (t2 - previous_x2 - sample_weight)
                        n = int(elapsed_delta)
                        if n > 0:
                            out = "no_samples " + str(n) + "\n"
                            f.write(out.encode())
                            line_num += 1
        f.close()


def write_timelines(stack_data):
    dt = stack_data.timeline_dt
    t1 = stack_data.timeline_start
    output_file = os.path.join(stack_data.path, stack_data.timelines_filename)
    f = open(output_file, 'wb')
    ids = stack_data.get_selected_process_ids()
    for task in stack_data.tasks:
        task_id = stack_data.tasks[task].task_id
        pids = []
        for id in ids:
            if id.task_id == task_id:
                pids.append((id.pid, id.tid))
        for pid, tid in pids:
            prev_stack = stack_data.timelines[task][pid][tid][0]
            count = 0
            start = t1
            for i in range(len(stack_data.timelines[task][pid][tid])):
                stack = stack_data.timelines[task][pid][tid][i]
                if stack == prev_stack:
                    count += 1
                else:
                    end = start + count * dt
                    out = "{}/{};{} {} {} {}\n".format(str(pid), str(tid), prev_stack, str(start), str(end), str(count))
                    f.write(out.encode())
                    count = 1
                    prev_stack = stack
                    start = end
            end = start + count * dt
            out = "{}/{};{} {} {} {}\n".format(str(pid), str(tid), prev_stack, str(start), str(end), str(count))
            f.write(out.encode())
            for i in range(len(stack_data.sample_rates[task][pid][tid])):
                time = t1 + (i + 0.5) * dt
                rate = stack_data.sample_rates[task][pid][tid][i]
                out = "sample-rate;{}/{} {} {}\n".format(str(pid), str(tid), str(time), str(rate))
                f.write(out.encode())
            if task in stack_data.secondary_events:
                if pid in stack_data.secondary_events[task]:
                    if tid in stack_data.secondary_events[task][pid]:
                        for event in stack_data.secondary_events[task][pid][tid]:
                            for time in stack_data.secondary_events[task][pid][tid][event]:
                                out = "secondary-event;{}/{} {} {}\n".format(str(pid), str(tid), event, str(time))
                                f.write(out.encode())
    f.close()
