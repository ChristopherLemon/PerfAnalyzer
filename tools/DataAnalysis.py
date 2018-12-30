__author__ = 'CLemon'

import re
import sys
from math import log10, atan, pi


class ClusterAnalysis:
    """"""

    def __init__(self):
        self.cluster_map = {}
        self.cluster_labels = []
        self.nclusters = 0
        self.blob = []

    def add_data(self, blob):
        self.blob = blob

    def calculate_ratios(self, n):
        self.cluster_labels = []
        self.nclusters = n
        xmax = -sys.maxsize
        ymax = -sys.maxsize
        for i, x in enumerate(self.blob):
            yi = x[0]
            xi = x[1]
            xmax = max(xmax, xi)
            ymax = max(ymax, yi)
        xmax = max(xmax, 1.0)
        ymax = max(ymax, 1.0)
        dt = 0.5 * pi / float(n)
        bins = [0.5 * pi - dt * float(i) for i in range(1, n + 1)]
        for x in self.blob:
            yi = x[0] / ymax
            xi = x[1] / xmax
            t = 0.0
            if xi == 0.0:
                if yi > 0.0:
                    t = 0.5 * pi
            else:
                t = atan(yi / xi)
            if t > 0.5 * pi or t < 0:
                self.cluster_labels.append(n)
            else:
                for j, b in enumerate(bins):
                    if b <= t:
                        self.cluster_labels.append(j)
                        break

    def get_cluster_labels(self):
        return self.cluster_labels

    def get_num_clusters(self):
        return self.nclusters


class ClusterFlameGraph:

    def __init__(self):
        self.stack_map = {}
        self.cluster_data = {}
        self.cluster_labels = {}
        self.cluster_map = {}

    def add_data(self, cluster_data, cluster_labels, cluster_map):
        self.cluster_data = cluster_data
        self.cluster_labels = cluster_labels
        self.cluster_map = cluster_map

    def get_flamegraph_colour_map(self, colours):
        colour_map = {}
        for job in self.cluster_data:
            for pid in self.cluster_data[job]:
                for tid in self.cluster_data[job][pid]:
                    for s in self.cluster_data[job][pid][tid]:
                        ci = self.cluster_map[job][pid][tid][s]
                        i = self.cluster_labels[ci]
                        if i >= 0:
                            k = i % len(colours)
                            v = colours[k]
                        else:
                            v = "rgb(224,224,224)"
                        node = s.rpartition(";")[2]
                        node += "[[cluster" + str(i) + "]]"
                        colour_map[node] = v
        return colour_map

    def make_stack_map(self, all_stack_data, clusters, append_cluster_labels, event1=None, event2=None,
                       xlower=None, xupper=None, ylower=None, yupper=None):
        self.stack_map = {}
        for stack_name in all_stack_data:
            self.stack_map[stack_name] = {}
            stack_data = all_stack_data[stack_name]
            ids = stack_data.get_selected_process_ids()
            for process_id in ids:
                job = process_id.job
                pid = process_id.pid
                tid = process_id.tid
                event_type = process_id.event_type
                if event_type == "original":
                    counts = stack_data.get_original_event_stack_data(process_id)
                    for stack in counts:
                        s = re.sub("(([\-0-9]+)/([0-9]+))", "", stack)
                        s = re.sub(job + ";", "", s)
                        node = s.rpartition(";")[2]
                        if node in self.cluster_map[job][pid][tid]:
                            ci = self.cluster_map[job][pid][tid][node]
                            i = self.cluster_labels[ci]
                            if i in clusters:
                                if xlower:
                                    count1 = self.cluster_data[job][pid][tid][node][event1]
                                    count2 = self.cluster_data[job][pid][tid][node][event2]
                                    if count1 < ylower or count1 > yupper or count2 < xlower or count2 > xupper:
                                        continue
                                if append_cluster_labels:
                                    new_stack = stack + "[[cluster" + str(i) + "]]"
                                    self.stack_map[stack_name][stack] = new_stack
                                else:
                                    self.stack_map[stack_name][stack] = stack
            stack_data.set_stack_map(self.stack_map[stack_name])


class GeneralAnalysis:

    def __init__(self):
        self.cluster_analysis = ClusterAnalysis()
        self.cluster_flamegraph = ClusterFlameGraph()
        self.nevents = 0
        self.all_stack_data = {}
        self.events = []
        self.cluster_events = {}
        self.min_base_sample_size = 1
        self.data = {}
        self.base_case_offsets = {}
        self.counter = {}
        self.event_index = {}
        self.cluster_data = {}
        self.cluster_map = {}
        self.base_case_offset = {}
        self.cluster_filter = []
        self.ncols = 0
        self.nrows = 0
        self.initialised = False

    def reset_stack_maps(self):
        for stack_data in self.all_stack_data.values():
            stack_data.set_stack_map(None)  # Reset current stack_map

    def set_events(self, cluster_events):
        self.cluster_events = cluster_events
        for e in self.cluster_events["All"]:
            label = e
            self.event_index[label] = len(self.event_index)
            self.events.append(label)
        for r in self.cluster_events['Ratios']:
            e1 = r[0]
            e2 = r[1]
            label = e1 + '-divide-' + e2
            self.event_index[label] = len(self.event_index)
            self.events.append(label)

    def add_data(self, stack_data, process):
        processes = [c.process for c in self.all_stack_data.values() if stack_data.data_view == "process"]
        if stack_data.process not in processes:
            self.all_stack_data[process] = stack_data

    def apply_log_scale(self):
        for job in self.cluster_data:
            for pid in self.cluster_data[job]:
                for tid in self.cluster_data[job][pid]:
                    for node in self.cluster_data[job][pid][tid]:
                        for e in self.cluster_data[job][pid][tid][node]:
                            x = self.cluster_data[job][pid][tid][node][e]
                            if x > 0.0:
                                self.cluster_data[job][pid][tid][node][e] = log10(x)

    def add_offset(self, reference_process):
        stack_data = self.all_stack_data[reference_process]
        base_case_id = stack_data.get_base_case_id()
        job = base_case_id.job
        pid = base_case_id.pid
        tid = base_case_id.tid
        self.base_case_offset = {}
        for node in self.cluster_data[job][pid][tid]:
            if node not in self.base_case_offset:
                self.base_case_offset[node] = {e: 0.0 for e in self.cluster_data[job][pid][tid][node]}
            for e in self.cluster_data[job][pid][tid][node]:
                self.base_case_offset[node][e] = self.cluster_data[job][pid][tid][node][e]
        for job in self.cluster_data:
            for pid in self.cluster_data[job]:
                for tid in self.cluster_data[job][pid]:
                    for node in self.cluster_data[job][pid][tid]:
                        if node in self.base_case_offset:
                            for e in self.cluster_data[job][pid][tid][node]:
                                offset = self.base_case_offset[node][e]
                                self.cluster_data[job][pid][tid][node][e] -= offset

    def make_data(self, reference_process, centred=False, log_scale=False):
        self.data = {}
        self.reset_stack_maps()
        for stack_data in self.all_stack_data.values():
            ids = stack_data.get_selected_process_ids()
            for process_id in ids:
                task_id = process_id.task_id
                job = process_id.job
                pid = process_id.pid
                tid = process_id.tid
                raw_event = process_id.raw_event
                if raw_event in self.cluster_events["All"]:
                    if job not in self.data:
                        self.data[job] = {}
                        self.counter[job] = {}
                    if pid not in self.data[job]:
                        self.data[job][pid] = {}
                        self.counter[job][pid] = {}
                    if tid not in self.data[job][pid]:
                        self.data[job][pid][tid] = {}
                        self.counter[job][pid][tid] = {}
                    self.counter[job][pid][tid] = stack_data.tasks[task_id].event_counter
                    counts = stack_data.get_original_event_stack_data(process_id)
                    for stack in counts:
                        s = re.sub("(([\-0-9]+)/([0-9]+))", "", stack)
                        s = re.sub(job + ";", "", s)
                        if s not in self.data[job][pid][tid]:
                            self.data[job][pid][tid][s] = {e: 0.0 for e in self.cluster_events["All"]}
                        self.data[job][pid][tid][s][raw_event] += counts[stack]

        self.ncols = len(self.cluster_events['Ratios'])
        self.nrows = 0
        self.cluster_data = {}
        for job in self.data:
            if job not in self.cluster_data:
                self.cluster_data[job] = {}
            for pid in self.data[job]:
                if pid not in self.cluster_data[job]:
                    self.cluster_data[job][pid] = {}
                for tid in self.data[job][pid]:
                    if tid not in self.cluster_data[job][pid]:
                        self.cluster_data[job][pid][tid] = {}
                    for s in self.data[job][pid][tid]:
                        node = s.rpartition(";")[2]
                        if node not in self.cluster_data[job][pid][tid]:
                            self.cluster_data[job][pid][tid][node] = {e: 0.0 for e in self.cluster_events["All"]}
                        for e in self.cluster_events["All"]:
                            v = self.data[job][pid][tid][s][e]
                            self.cluster_data[job][pid][tid][node][e] += float(v)
                            self.nrows += 1
        if len(self.cluster_events['Ratios']) > 0:
            for job in self.cluster_data:
                for pid in self.cluster_data[job]:
                    for tid in self.cluster_data[job][pid]:
                        for node in self.cluster_data[job][pid][tid]:
                            for r in self.cluster_events['Ratios']:
                                e1 = r[0]
                                e2 = r[1]
                                r1 = self.cluster_data[job][pid][tid][node][e1]
                                r2 = self.cluster_data[job][pid][tid][node][e2]
                                v = 0.0
                                if r2 > 0.0:
                                    v = r1 / r2
                                e = e1 + '-divide-' + e2
                                self.cluster_data[job][pid][tid][node][e] = v
                                self.nrows += 1
        if log_scale:
            self.apply_log_scale()
        if centred:
            self.add_offset(reference_process)

    def setup_cluster_analysis(self, event1, event2, xlower=None, xupper=None, ylower=None, yupper=None):
        n = 0
        self.cluster_map = {}
        self.cluster_analysis.blob = []
        for job in self.cluster_data:
            if job not in self.cluster_map:
                self.cluster_map[job] = {}
            for pid in self.cluster_data[job]:
                if pid not in self.cluster_map[job]:
                    self.cluster_map[job][pid] = {}
                for tid in self.cluster_data[job][pid]:
                    if tid not in self.cluster_map[job][pid]:
                        self.cluster_map[job][pid][tid] = {}
                    for node in self.cluster_data[job][pid][tid]:
                        count1 = self.cluster_data[job][pid][tid][node][event1]
                        count2 = self.cluster_data[job][pid][tid][node][event2]
                        if xlower:
                            if count1 < ylower or count1 > yupper or count2 < xlower or count2 > xupper:
                                continue
                        if node not in self.cluster_map[job][pid][tid]:
                            self.cluster_map[job][pid][tid][node] = n
                        x = [count1, count2]
                        self.cluster_analysis.blob.append(x)
                        n += 1

    def write_flamegraph_colour_map(self, working_dir, colours):
        self.cluster_flamegraph.write_flamegraph_colour_map(working_dir, colours)

    def make_stack_map(self, clusters, append_cluster_labels, event1=None, event2=None, xlower=None,
                       xupper=None, ylower=None, yupper=None):
        self.cluster_flamegraph.make_stack_map(self.all_stack_data, clusters, append_cluster_labels, event1=event1,
                                               event2=event2, xlower=xlower, xupper=xupper, ylower=ylower,
                                               yupper=yupper)

    def calculate_ratios(self, n, event1, event2, xlower, xupper, ylower, yupper):
        self.setup_cluster_analysis(event1, event2, xlower, xupper, ylower, yupper)
        self.cluster_analysis.calculate_ratios(n)
        self.cluster_filter = [i for i in range(0, n)]
        self.cluster_flamegraph.add_data(self.cluster_data, self.cluster_analysis.cluster_labels, self.cluster_map)
        self.initialised = True

    def get_stack_data(self):
        return self.all_stack_data

    def get_flamegraph_colour_map(self, colours):
        return self.cluster_flamegraph.get_flamegraph_colour_map(colours)

    def get_index(self, event):
        return self.event_index[event]

    def get_events(self):
        return self.events

    def get_cluster_data(self):
        data = {}
        if len(self.cluster_filter) < self.get_num_clusters():
            for job in self.cluster_data:
                data[job] = {}
                for pid in self.cluster_data[job]:
                    data[job][pid] = {}
                    for tid in self.cluster_data[job][pid]:
                        data[job][pid][tid] = {}
                        for node in self.cluster_data[job][pid][tid]:
                            ci = self.cluster_map[job][pid][tid][node]
                            i = self.cluster_analysis.cluster_labels[ci]
                            if i in self.cluster_filter:
                                if node not in self.data:
                                    data[job][pid][tid][node] = {}
                                for e in self.cluster_data[job][pid][tid][node]:
                                    data[job][pid][tid][node][e] = self.cluster_data[job][pid][tid][node][e]
            return data
        else:
            return self.cluster_data

    def get_cluster_events(self):
        return self.cluster_events

    def get_cluster_labels(self):
        return self.cluster_analysis.cluster_labels

    def get_cluster_map(self):
        return self.cluster_map

    def get_num_clusters(self):
        return self.cluster_analysis.nclusters

    def set_cluster_filter(self, clusters):
        self.cluster_filter = clusters
