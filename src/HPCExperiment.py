import re
import sys
import pathlib
import os
from pathlib import Path
from lxml import etree

from src.ColourMaps import get_top_ten_colours


def is_hpc_result(results_file):
    filename = re.sub("\.results", ".frames", results_file)
    return os.path.exists(filename)


class HPCExperimentHandler:

    def __init__(self, results_dir, experiment):
        self.results_dir = results_dir
        self.experiment_file = experiment
        self.job_id = pathlib.Path(experiment).parent.name
        self.detail = "loops"
        self.results_file = ""

    def create_results(self, include_loops=True, include_statements=False):
        if include_statements:
            self.detail = "lines"
        elif include_loops:
            self.detail = "loops"
        else:
            self.detail = "functions"
        self.results_file = os.path.join(self.results_dir, self.job_id) + "_" + self.detail + ".results"
        f = open(self.results_file, "wb")
        f.write("cpu_id:General\n".encode())
        f.write("time_interval:1.00\n".encode())
        hpc_experiment = HPCExperiment(self.results_dir, self.job_id + "_" + self.detail)
        hpc_experiment.read_experiment(self.experiment_file, include_loops, include_statements)
        hpc_experiment.process_experiment()
        metrics = hpc_experiment.get_metrics()
        results = hpc_experiment.get_results()
        for metric in metrics:
            info = "event_counter-" + metric.lower() + ":run-" + str(1) + ":" + str(1) + "\n"
            f.write(info.encode())
        for result in results:
            out = result + "\n"
            f.write(out.encode())
        f.close()
        return self.results_file

    def get_results_file_name(self):
        return self.results_file

    def get_experiment_file_name(self):
        return self.experiment_file


class HPCResultsHandler:

    def __init__(self, results_dir, results_file):
        self.results_dir = results_dir
        self.job_id = pathlib.Path(results_file).stem
        self.frames_file = os.path.join(self.results_dir, self.job_id) + ".frames"
        self.results_file = results_file
        self.frames = self.load_frames()

    def load_frames(self):
        frames = {}
        with open(self.frames_file) as f:
            for line in f.readlines():
                match = re.match("(.*) (.*)@([0-9]+)\n", line)
                if match:
                    frame = match.group(1)
                    file = match.group(2)
                    line = match.group(3)
                    frames[frame] = (file, line)
        return frames

    def get_frames(self):
        return self.frames

    def get_job_id(self):
        return self.job_id


class HPCExperiment:

    def __init__(self, results_dir, job_id):
        self.results_dir = results_dir
        self.job_id = job_id
        self.file_map = {}
        self.colormap = {}
        self.procedure_map = {}
        self.metric_to_results_map = {}
        self.experiment_file = None
        self.include_loops = True
        self.include_statements = False
        self.experiment_tree = None
        self.frames = {}
        self.metrics = {}
        self.results_files = {}
        self.color_map = {}
        self.header = ""
        self.metric_info = None
        self.parser = etree.XMLParser(huge_tree=True) # Nesting level can be excessively high!

    def read_experiment(self, experiment_file, include_loops=True, include_statements=False):
        self.experiment_file = experiment_file
        self.include_loops = include_loops
        self.include_statements = include_statements
        self.experiment_tree = etree.parse(experiment_file, parser=self.parser)
        self.procedure_map = self.get_procedure_names(self.experiment_tree)
        self.file_map = self.get_file_names(self.experiment_tree)

    def process_experiment(self):
        self.frames = {}
        self.metrics = {}
        self.results_files = {}
        self.header = self.find_header()
        self.metric_info = self.find_metric_info()
        colors = get_top_ten_colours()
        previous_stack_trace = {}
        current_stack_trace = {}
        self.color_map = {}
        current_count = {}
        current_stack = [""]
        walk_experiment = self.experiment_tree.getiterator()
        for elt in walk_experiment:
            node_level = self.get_node_level(elt)
            if node_level < len(current_stack):
                n = len(current_stack) - node_level
                del current_stack[-n:]
            if elt.tag == 'PF':
                name = elt.attrib['n']
                p_name = self.procedure_map[name]
                if node_level == len(current_stack):
                    current_stack[-1] = p_name
                else:
                    current_stack.append(p_name)
            elif self.include_loops and elt.tag == 'L':
                line = elt.attrib['l']
                p_name = self.get_procedure_name(elt, self.procedure_map)
                unique_id = "Loop@" + str(line) + "@" + p_name
                self.color_map[unique_id] = colors[8]
                if node_level == len(current_stack):
                    current_stack[-1] = unique_id
                else:
                    current_stack.append(unique_id)
            elif self.include_statements and elt.tag == 'S':
                line = elt.attrib['l']
                p_name = self.get_procedure_name(elt, self.procedure_map)
                unique_id = "Line@" + str(line) + "@" + p_name
                self.color_map[unique_id] = colors[0]
                if node_level == len(current_stack):
                    current_stack[-1] = unique_id
                else:
                    current_stack.append(unique_id)
            elif elt.tag == 'M':
                n = elt.attrib['n']
                if n in self.metric_info:
                    stack_trace = ";".join(current_stack[1:])
                    stack_trace = re.sub(" ", "", stack_trace)
                    metric_info = self.metric_info[n]
                    metric = metric_info[0]
                    process = metric_info[1]
                    thread = metric_info[2]
                    period = metric_info[3]
                    unique_id = (metric, process, thread)
                    if unique_id not in current_count:
                        current_count[unique_id] = 0
                        previous_stack_trace[unique_id] = stack_trace
                    current_stack_trace[unique_id] = stack_trace
                    if current_count[unique_id] > 0 and \
                            current_stack_trace[unique_id] != previous_stack_trace[unique_id]:
                        if metric not in self.metrics:
                            self.metrics[metric] = period
                        out = "{}-{}/{};{} {}\n"\
                            .format(self.header, process, thread, previous_stack_trace[unique_id],
                                    str(current_count[unique_id]))
                        frame = current_stack[-1]
                        frame = re.sub(" ", "", frame)
                        self.frames[frame] = self.unwind_frame_details(elt, self.file_map)
                        filename = self.get_results_file_name(metric, process)
                        if filename not in self.results_files:
                            self.results_files[filename] = open(filename, 'wb')
                            self.results_files[filename].write("t=0.00\n".encode())
                        self.results_files[filename].write(out.encode())
                        current_count[unique_id] = 0
                        previous_stack_trace[unique_id] = current_stack_trace[unique_id]
                    total = int(round(float(elt.attrib['v'])))
                    current_count[unique_id] += total
        for unique_id in current_stack_trace:
            metric = unique_id[0]
            process = unique_id[1]
            thread = unique_id[2]
            out = "{}-{}/{};{} {}\n"\
                .format(self.header, process, thread, current_stack_trace[unique_id], str(current_count[unique_id]))
            filename = self.get_results_file_name(metric, process)
            if filename not in self.results_files:
                self.results_files[filename] = open(filename, 'wb')
                self.results_files[filename].write(out.encode())
        for filename in self.results_files:
            self.results_files[filename].write("t=1.00\n".encode())
            self.results_files[filename].close()
        self.write_file_map()

    def write_file_map(self):
        filename = os.path.join(self.results_dir, self.job_id) + ".frames"
        f = open(filename, 'wb')
        for frame in self.frames:
            info = self.frames[frame]
            file = info[0]
            line = info[1]
            database_location = os.path.dirname(self.experiment_file)
            path = os.path.relpath(os.path.join(database_location, Path(file)), self.results_dir)
            out = "{} {}@{}\n".format(frame, path, line)
            f.write(out.encode())
        f.close

    def get_color_map(self):
        return self.color_map

    def find_header(self):
        root = self.experiment_tree.getroot()
        return root.find('.//Header').attrib['n']

    def get_header(self):
        return self.header

    def get_results_file_name(self, metric, process):
        name = self.job_id + "_proc" + str(process) + "_" + metric.lower()
        results_file = os.path.join(self.results_dir, name)
        return results_file

    def get_metric_info(self):
        return self.get_metric_info

    def get_results(self):
        results = set()
        for result in self.results_files:
            file = os.path.basename(result)
            results.add(file)
        return results

    def get_metrics(self):
        return self.metrics

    def find_metric_info(self):
        root = self.experiment_tree.getroot()
        pt = root.find('.//MetricTable')
        metric_info = {}
        for f in pt.findall('Metric'):
            it = f.getiterator()
            for elt in it:
                if "n" in elt.attrib:
                    n = elt.attrib["n"]
                    if n == "period":
                        period = elt.attrib["v"]
            n = f.attrib['n']
            i = f.attrib['i']
            match = re.match("(.*)\.\[([0-9]+),([0-9]+)\]", n)
            if match:
                metric = match.group(1)
                process = match.group(2)
                thread = match.group(3)
                metric_info[i] = (metric, process, thread, period)
                filename = self.get_results_file_name(metric, process)
                self.metric_to_results_map[i] = filename
        return metric_info

    @staticmethod
    def get_file_names(experiment_tree):
        file_map = {}
        root = experiment_tree.getroot()
        pt = root.find('.//FileTable')
        for f in pt.findall('File'):
            i = f.attrib['i']
            n = f.attrib['n']
            file_map[i] = n
        return file_map

    @staticmethod
    def get_procedure_names(experiment_tree):
        procedure_map = {}
        root = experiment_tree.getroot()
        pt = root.find('.//ProcedureTable')
        for f in pt.findall('Procedure'):
            i = f.attrib['i']
            n = f.attrib['n']
            procedure_map[i] = n
        return procedure_map

    @staticmethod
    def get_procedure_name(node, procedure_map):
        nd = node
        while nd is not None:
            if nd.tag == "PF":
                name = nd.attrib['n']
                return procedure_map[name]
            nd = nd.getparent()

    def get_file_info(self, frame):
        return self.frames[frame]

    def unwind_frame_details(self, node, file_map):
        nd = node
        line = None
        file = None
        while nd is not None:
            if nd.tag == "PF":
                f = nd.attrib['f']
                file = file_map[f]
                if not line:
                    line = nd.attrib['l']
            elif self.include_loops and nd.tag == "L":
                f = nd.attrib['f']
                file = file_map[f]
                if not line:
                    line = nd.attrib['l']
            elif self.include_statements and nd.tag == "S":
                line = nd.attrib['l']
            if line and file:
                return file, line
            nd = nd.getparent()

    def get_node_level(self, node):
        d = 1
        nd = node
        while nd is not None:
            if nd.tag == "PF":
                d += 1
            elif self.include_loops and nd.tag == "L":
                d += 1
            elif self.include_statements and nd.tag == "S":
                d += 1
            if nd.tag == "SecCallPathProfileData":
                return d
            nd = nd.getparent()
        return sys.maxsize
