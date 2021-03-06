import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from collections import OrderedDict, defaultdict
from timeit import default_timer as timer

from src.Utilities import natural_sort
from src.CustomEvents import (
    event_to_raw_event,
    raw_event_to_event,
    get_event_type,
    create_custom_event_stack,
    is_composite_event,
)
from src.ResultsHandler import get_job_name, get_event_counters


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
    return task.X, task.Y


class StackDataID:
    """Metadata for collapsed stacks data for a specific job, event, process, and thread."""

    def __init__(
        self,
        job,
        label,
        task_id,
        pid,
        tid,
        process_name,
        event_name,
        raw_event,
        event_type,
    ):
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
    def __init__(
        self,
        task_id,
        filename,
        job,
        process_name,
        event,
        raw_event,
        event_type,
        counter,
        time_interval,
    ):
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
                        stack, _, secondary = stack.rpartition(" ")
                    stack, _, primary = stack.rpartition(" ")
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
                                        self.stacks[pid][tid][stack][0] += self.work[
                                            pid
                                        ][tid][stack][0]
                                        self.stacks[pid][tid][stack][1] += self.work[
                                            pid
                                        ][tid][stack][1]
                                    else:
                                        if stack not in self.stacks[pid][tid]:
                                            self.stacks[pid][tid][stack] = [0, 0]
                                        self.stacks[pid][tid][stack][0] += self.work[
                                            pid
                                        ][tid][stack][0]
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
                        r = float(self.event_counter) * float(c0) / dt
                    self.Y[pid][tid].append(r)

    def write_stacks(self):
        output_file = self.filename + "_compressed"
        f = open(output_file, "wb")
        for pid in self.stacks:
            for tid in self.stacks[pid]:
                for stack in self.stacks[pid][tid]:
                    if self.event_type == "custom_event_ratio":
                        out = (
                            stack
                            + " "
                            + str(self.stacks[pid][tid][stack][0])
                            + " "
                            + str(self.stacks[pid][tid][stack][1])
                            + "\n"
                        )
                    else:
                        out = stack + " " + str(self.stacks[pid][tid][stack][0]) + "\n"
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

    def __init__(
        self,
        results_files,
        path,
        cpu_definition,
        event=None,
        process=None,
        debug=True,
        n_proc=1,
    ):
        self.selected_ids = []
        self.all_jobs = []
        self.start = -1.0
        self.cpu_definition = cpu_definition
        self.results_files = results_files
        self.stack_file = ""
        self.event_counters = {}
        self.path = path
        self.system_wide = False
        self.min_x = sys.float_info.max
        self.max_x = -sys.float_info.max
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
        self.event = event
        self.process = process
        if self.event:  # Check for composite event
            if is_composite_event(self.event):
                create_custom_event_stack(self, results_files, self.event)
                self.event_counters = get_event_counters(
                    path, results_files
                )  # Update counters with new custom event
        assert not (event and process)
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
        if self.event:
            self.set_biggest_process_ids_for_each_job()
            self.base_case = self.get_dominant_id(self.default_ids).label
        if self.process:
            self.base_case = self.get_dominant_id(self.selected_ids).label
        self.flamegraph_process_ids = [self.get_base_case_id()]
        self.start = self.get_min_x()
        self.stop = self.get_max_x()
        self.text_filter = ""

    @classmethod
    def create_event_data(
        cls, results_files, path, cpu_definition, data_id="", debug=True, n_proc=1
    ):
        """Create event view of data, containing stack counts for the event across all
        jobs, processes and threads."""
        event = event_to_raw_event(data_id, cpu_definition)
        return cls(
            results_files, path, cpu_definition, event=event, debug=debug, n_proc=n_proc
        )

    @classmethod
    def create_process_data(
        cls, results_files, path, cpu_definition, data_id="", debug=True, n_proc=1
    ):
        """Create process view of data, containing stack counts across all events and threads
        within a process."""
        process = data_id
        return cls(
            results_files,
            path,
            cpu_definition,
            process=process,
            debug=debug,
            n_proc=n_proc,
        )

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
                        if (
                            self.process
                            and self.process == process
                            or self.event
                            and self.event == raw_event
                        ):
                            self.tasks[task_id] = ReadStacksTask(
                                task_id,
                                full_path,
                                job,
                                process_name,
                                event,
                                raw_event,
                                event_type,
                                counter,
                                self.time_interval,
                            )

    def data_update_required(self, start, stop):
        if self.start >= 0.0:
            update = False
            update = update or start != self.start
            update = update or stop != self.stop
        else:
            update = True
        return update

    def read_data(
        self,
        start=0.0,
        stop=sys.float_info.max,
        text_filter="",
        selected_ids=None,
        base_case="",
        initialise=False,
    ):
        """Read in all stack data for the event or process, applying filters for the
        selected time range, call stack text match, and selected events, processes 
        and threads."""
        selected_ids = [] if selected_ids is None else selected_ids
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
            pool = ProcessPoolExecutor(min(self.n_proc, len(self.tasks)))
            arg_list = []
            for task in self.tasks:
                new_task = self.tasks[task]
                arg_list.append((new_task, start_time, stop_time))
            finished_tasks = list(pool.map(multi_run_wrapper, arg_list))
        else:
            finished_tasks = []
            for task in self.tasks:
                new_task = self.tasks[task]
                finished_tasks.append(worker(new_task, start_time, stop_time))

        task_num = 0
        for task in self.tasks:
            new_task = self.tasks[task]
            task_id = new_task.task_id
            finished_task = finished_tasks[task_num]
            self.X[task_id], self.Y[task_id] = finished_task
            task_num += 1

        self.compute_totals()

        for task in self.X:
            for pid in self.X[task]:
                for tid in self.X[task][pid]:
                    for x in self.X[task][pid][tid]:
                        self.min_x = min(self.min_x, x)
                        self.max_x = max(self.max_x, x)
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
            process = self.tasks[task].process_name
            event = self.tasks[task].event
            self.totals[task_id] = {}
            self.count[task_id] = {}
            counter = self.tasks[task_id].event_counter
            event_type = self.tasks[task].event_type
            input_file = self.tasks[task].filename + "_compressed"
            fin = open(input_file, "r")
            for line in fin:
                k = keyword.search(line)
                if k:
                    stack = line.strip()
                    match = re.search(process_id_regex, line)
                    if match:
                        pid = match.group(2)
                        tid = match.group(3)
                        label = make_label(job, process, event, pid, tid)
                        if pid not in self.totals[task_id]:
                            self.totals[task_id][pid] = {}
                            self.count[task_id][pid] = {}
                        if tid not in self.totals[task_id][pid]:
                            self.totals[task_id][pid][tid] = 0.0
                            self.count[task_id][pid][tid] = [0, 0]
                        if event_type == "custom_event_ratio":
                            stack, _, secondary = stack.rpartition(" ")
                        stack, _, primary = stack.rpartition(" ")
                        c0 = int(primary)
                        if event_type == "custom_event_ratio":
                            c1 = int(secondary)
                        else:
                            c1 = c0
                        if self.stack_map:
                            line = label + ";" + stack
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

    def get_all_process_ids(self):
        return self.ordered_ids

    def get_dominant_id(self, ids):
        max_percentage = 0.0
        for process_id in ids:
            if self.process and process_id.event_type == "custom_event_ratio":
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

    def get_process_id_from_label(self, label):
        proc_id = None
        for process_id in self.ordered_ids:
            if process_id.label == label:
                proc_id = process_id
        return proc_id

    def get_initial_process_ids(self):
        process_ids = []
        for process_id in self.ordered_ids:
            pid = process_id.pid
            tid = process_id.tid
            if self.system_wide:  # Monitor cores
                if (
                    pid != "all" and tid == "all"
                ):  # One id for each core, including all threads on the core
                    process_ids.append(process_id)
            else:  # Monitor application threads
                if tid != "all":  # One id for each thread of the application
                    process_ids.append(process_id)
        if (
            len(process_ids) == 0
        ):  # No thread/core ids selected - add whatever is selected
            for process_id in self.ordered_ids:
                process_ids.append(process_id)
        return process_ids

    def set_process_ids(self):
        vals = [
            process_id.label for process_id in self.ordered_ids
        ]  # Store previous ids
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
                        self.ordered_ids.append(
                            StackDataID(
                                job,
                                label,
                                task,
                                pid,
                                tid,
                                process_name,
                                event_name,
                                raw_event,
                                event_type,
                            )
                        )
        self.ordered_ids = natural_sort(
            self.ordered_ids, key=lambda process_id: process_id.label
        )
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
                    if self.event:
                        total_count[0] += process_id.count2
                else:
                    total_count[0] += process_id.count1
            elif pid != "all":
                max_count1[1] = max(max_count1[1], process_id.count1)
                max_count2[1] = max(max_count2[1], process_id.count2)
                if event_type == "custom_event_ratio":
                    if self.event:
                        total_count[1] += process_id.count2
                else:
                    total_count[1] += process_id.count1
            else:
                max_count1[2] = max(max_count1[2], process_id.count1)
                max_count2[2] = max(max_count2[2], process_id.count2)
                if event_type == "custom_event_ratio":
                    if self.event:
                        total_count[2] += process_id.count2
                else:
                    total_count[2] += process_id.count1
        for process_id in self.ordered_ids:
            pid = process_id.pid
            tid = process_id.tid
            event_type = process_id.event_type
            if pid != "all" and tid != "all":
                if event_type == "custom_event_ratio":
                    process_id.total_percentage = (
                        100.0 * float(process_id.count2) / float(total_count[0])
                    )
                    process_id.max_percentage = (
                        100.0 * float(process_id.count2) / float(max_count2[0])
                    )
                else:
                    process_id.total_percentage = (
                        100.0 * float(process_id.count1) / float(total_count[0])
                    )
                    process_id.max_percentage = (
                        100.0 * float(process_id.count1) / float(max_count1[0])
                    )
            elif pid != "all":
                if event_type == "custom_event_ratio":
                    process_id.total_percentage = (
                        100.0 * float(process_id.count2) / float(total_count[1])
                    )
                    process_id.max_percentage = (
                        100.0 * float(process_id.count2) / float(max_count2[1])
                    )
                else:
                    process_id.total_percentage = (
                        100.0 * float(process_id.count1) / float(total_count[1])
                    )
                    process_id.max_percentage = (
                        100.0 * float(process_id.count1) / float(max_count1[1])
                    )
            else:
                if event_type == "custom_event_ratio":
                    process_id.total_percentage = (
                        100.0 * float(process_id.count2) / float(total_count[2])
                    )
                    process_id.max_percentage = (
                        100.0 * float(process_id.count2) / float(max_count2[2])
                    )
                else:
                    process_id.total_percentage = (
                        100.0 * float(process_id.count1) / float(total_count[2])
                    )
                    process_id.max_percentage = (
                        100.0 * float(process_id.count1) / float(max_count1[2])
                    )

    def get_system_wide_mode_enabled(self):
        return self.system_wide

    def get_collapsed_stacks_filename(self):
        return self.collapsed_stacks_filename

    def get_min_x(self):
        return self.min_x

    def get_max_x(self):
        return self.max_x

    def reset_cached_data(self):
        self.filtered_stacks_x = {}
        self.filtered_stacks_y = {}
        self.filtered_stacks = {}

    def get_custom_event_ratio_stack_data(self, process_id):
        keyword = re.compile(self.text_filter)
        process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
        task_id = process_id.task_id
        counter = float(self.tasks[task_id].event_counter)
        pid = process_id.pid
        tid = process_id.tid
        if task_id in self.filtered_stacks_x:
            if pid in self.filtered_stacks_x[task_id]:
                if tid in self.filtered_stacks_x[task_id][pid]:  # Return cached data
                    return (
                        self.filtered_stacks_x[task_id][pid][tid],
                        self.filtered_stacks_y[task_id][pid][tid],
                    )
        else:
            self.filtered_stacks_x[task_id] = {}
            self.filtered_stacks_y[task_id] = {}
        ids = self.ordered_ids
        pids = {
            (proc_id.pid, proc_id.tid): proc_id.label
            for proc_id in ids
            if proc_id.task_id == task_id
        }
        input_file = self.tasks[task_id].filename + "_compressed"
        fin = open(input_file, "r")
        for line in fin:
            k = keyword.search(line)
            if k:
                match = re.search(process_id_regex, line)
                if match:
                    pid = match.group(2)
                    tid = match.group(3)
                    label = pids[(pid, tid)]
                    if pid not in self.filtered_stacks_x[task_id]:
                        self.filtered_stacks_x[task_id][pid] = {}
                        self.filtered_stacks_y[task_id][pid] = {}
                    if tid not in self.filtered_stacks_x[task_id][pid]:
                        self.filtered_stacks_x[task_id][pid][tid] = {}
                        self.filtered_stacks_y[task_id][pid][tid] = {}
                    stack, _, count2 = line.rpartition(" ")
                    stack, _, count1 = stack.rpartition(" ")
                    s = label + ";" + stack
                    if self.stack_map:
                        line = label + ";" + stack
                        if line in self.stack_map:
                            self.filtered_stacks_x[task_id][pid][tid][
                                s
                            ] = counter * float(count2)
                            self.filtered_stacks_y[task_id][pid][tid][
                                s
                            ] = counter * float(count1)
                    else:
                        self.filtered_stacks_x[task_id][pid][tid][s] = counter * float(
                            count2
                        )
                        self.filtered_stacks_y[task_id][pid][tid][s] = counter * float(
                            count1
                        )
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
        return (
            self.filtered_stacks_x[task_id][pid][tid],
            self.filtered_stacks_y[task_id][pid][tid],
        )

    def get_original_event_stack_data(self, process_id):
        keyword = re.compile(self.text_filter)
        process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
        task_id = process_id.task_id
        counter = float(self.tasks[task_id].event_counter)
        pid = process_id.pid
        tid = process_id.tid
        if task_id in self.filtered_stacks:
            if pid in self.filtered_stacks[task_id]:
                if tid in self.filtered_stacks[task_id][pid]:  # Return cached data
                    return self.filtered_stacks[task_id][pid][tid]
        else:
            self.filtered_stacks[task_id] = {}
        ids = self.ordered_ids
        pids = {
            (proc_id.pid, proc_id.tid): proc_id.label
            for proc_id in ids
            if proc_id.task_id == task_id
        }
        input_file = self.tasks[task_id].filename + "_compressed"
        fin = open(input_file, "r")
        for line in fin:
            k = keyword.search(line)
            if k:
                match = re.search(process_id_regex, line)
                if match:
                    pid = match.group(2)
                    tid = match.group(3)
                    label = pids[(pid, tid)]
                    if pid not in self.filtered_stacks[task_id]:
                        self.filtered_stacks[task_id][pid] = {}
                    if tid not in self.filtered_stacks[task_id][pid]:
                        self.filtered_stacks[task_id][pid][tid] = {}
                    stack, _, count1 = line.rpartition(" ")
                    s = label + ";" + stack
                    if self.stack_map:
                        line = label + ";" + stack
                        if line in self.stack_map:
                            self.filtered_stacks[task_id][pid][tid][
                                s
                            ] = counter * float(count1)
                    else:
                        self.filtered_stacks[task_id][pid][tid][s] = counter * float(
                            count1
                        )
        fin.close()
        pid = process_id.pid
        tid = process_id.tid
        # Return empty container if no match found
        if pid not in self.filtered_stacks[task_id]:
            self.filtered_stacks[task_id][pid] = {}
        if tid not in self.filtered_stacks[task_id][pid]:
            self.filtered_stacks[task_id][pid][tid] = {}
        return self.filtered_stacks[task_id][pid][tid]


def write_flamegraph_stacks(
    stack_data, flamegraph_type, append=False, output_event_type="original"
):
    keyword = re.compile(stack_data.text_filter)
    process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")

    output_file = os.path.join(stack_data.path, stack_data.collapsed_stacks_filename)
    if append:
        f = open(output_file, "ab")
    else:
        f = open(output_file, "wb")

    if flamegraph_type == "exclusive_diff":
        data = OrderedDict()
        base_symbols = {}
        symbols = {}
        base_case_id = stack_data.get_base_case_id()
        base_label = base_case_id.label
        ids = stack_data.get_flamegraph_process_ids()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            pids = {
                (proc_id.pid, proc_id.tid): proc_id.label
                for proc_id in ids
                if proc_id.task_id == task_id
            }
            if len(pids) > 0:
                input_file = stack_data.tasks[task].filename + "_compressed"
                fin = open(input_file, "r")
                for line in fin:
                    k = keyword.search(line)
                    if k:
                        match = re.search(process_id_regex, line)
                        if match:
                            p = match.group(2)
                            t = match.group(3)
                            if (p, t) in pids:
                                label = pids[(p, t)]
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
        for label in data:
            for stack in data[label]:
                symbol = stack.rpartition(";")[2]
                s = re.sub("((\-all|[\-0-9]+)/(all|[0-9]+))", "", stack)
                count = int(data[label][stack])
                base_count = 0
                if symbol in symbols[base_label]:
                    r = float(symbols[base_label][symbol]) / float(
                        symbols[label][symbol]
                    )
                    base_count = int(r * float(count))
                ll = label + ";" + s + " " + str(base_count) + " " + str(count) + "\n"
                f.write(ll.encode())
    elif flamegraph_type == "inclusive_diff":
        raw_stacks = defaultdict(dict)
        data = OrderedDict()
        base_case_id = stack_data.get_base_case_id()
        base_label = base_case_id.label
        ids = stack_data.get_flamegraph_process_ids()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            pids = {
                (proc_id.pid, proc_id.tid): proc_id.label
                for proc_id in ids
                if proc_id.task_id == task_id
            }
            if len(pids) > 0:
                input_file = stack_data.tasks[task].filename + "_compressed"
                fin = open(input_file, "r")
                for line in fin:
                    k = keyword.search(line)
                    if k:
                        match = re.search(process_id_regex, line)
                        if match:
                            p = match.group(2)
                            t = match.group(3)
                            if (p, t) in pids:
                                label = pids[(p, t)]
                                if label not in data:
                                    data[label] = OrderedDict()
                                stack, par, count = line.strip().rpartition(" ")
                                data[label][stack] = count
                                s = re.sub("((\-all|[\-0-9]+)/(all|[0-9]+))", "", stack)
                                raw_stacks[label][s] = count
                fin.close()
        for label in data:
            for stack in data[label]:
                s = re.sub("((\-all|[\-0-9]+)/(all|[0-9]+))", "", stack)
                base_count = 0
                count = data[label][stack]
                if s in raw_stacks[base_label]:
                    base_count = raw_stacks[base_label][s]
                ll = label + ";" + s + " " + str(base_count) + " " + str(count) + "\n"
                f.write(ll.encode())
            for stack in data[base_label]:
                s = re.sub("((\-all|[\-0-9]+)/(all|[0-9]+))", "", stack)
                count = 0
                base_count = data[base_label][stack]
                if s not in raw_stacks[label]:
                    ll = (
                        label
                        + ";"
                        + s
                        + " "
                        + str(base_count)
                        + " "
                        + str(count)
                        + "\n"
                    )
                    f.write(ll.encode())
    elif flamegraph_type == "plot_for_process":
        ids = stack_data.get_flamegraph_process_ids()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            event_type = stack_data.tasks[task].event_type
            pids = {
                (proc_id.pid, proc_id.tid): proc_id.label
                for proc_id in ids
                if proc_id.task_id == task_id
            }
            if len(pids) > 0:
                if event_type == output_event_type:
                    input_file = stack_data.tasks[task].filename + "_compressed"
                    fin = open(input_file, "r")
                    for line in fin:
                        k = keyword.search(line)
                        if k:
                            match = re.search(process_id_regex, line)
                            if match:
                                p = match.group(2)
                                t = match.group(3)
                                if (p, t) in pids:
                                    if event_type == "custom_event_ratio":
                                        ll = pids[(p, t)] + ";" + line
                                        f.write(ll.encode())
                                    else:
                                        if stack_data.stack_map:
                                            stack, par, count1 = line.rpartition(" ")
                                            line = pids[(p, t)] + ";" + stack
                                            if line in stack_data.stack_map:
                                                ll = (
                                                    stack_data.stack_map[line]
                                                    + " "
                                                    + count1
                                                )
                                                f.write(ll.encode())
                                        else:
                                            ll = pids[(p, t)] + ";" + line
                                            f.write(ll.encode())
                    fin.close()
    elif flamegraph_type == "plot_for_event":
        ids = stack_data.get_flamegraph_process_ids()
        for task in stack_data.tasks:
            task_id = stack_data.tasks[task].task_id
            pids = {
                (proc_id.pid, proc_id.tid): proc_id.label
                for proc_id in ids
                if proc_id.task_id == task_id
            }
            if len(pids) > 0:
                input_file = stack_data.tasks[task].filename + "_compressed"
                fin = open(input_file, "r")
                for line in fin:
                    k = keyword.search(line)
                    if k:
                        match = re.search(process_id_regex, line)
                        if match:
                            p = match.group(2)
                            t = match.group(3)
                            if (p, t) in pids:
                                ll = pids[(p, t)] + ";" + line
                                f.write(ll.encode())
                fin.close()
    f.close()
