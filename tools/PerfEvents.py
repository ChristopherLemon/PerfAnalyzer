__author__ = 'CLemon'
from collections import namedtuple, OrderedDict
from tools.Utilities import round_sig, natural_sort
from tools.CustomEvents import add_custom_events_to_active_events, raw_event_to_event, get_event_type
import tools.GlobalData
from tempfile import mkstemp
from shutil import move
import copy
import os
import re
import operator

EventDefinition = namedtuple('EventDefinition',
                             ['event',
                              'raw_event',
                              'event_group',
                              'unit',
                              'default',
                              'event_weight'])

event_definitions = OrderedDict()
roofline_events = {}

def initialise_cpu_definitions():
    perf_events_location = tools.GlobalData.perf_events
    cpus = OrderedDict()
    for f in os.listdir(perf_events_location):
        cpu, dot, ext = f.rpartition(".")
        if ext == "events":
            cpus[cpu] = f
    for cpu in cpus:
        f = cpus[cpu]
        full_filename = os.path.join(perf_events_location, f)
        event_definitions[cpu] = []
        has_roofline_events = False
        try:
            with open(full_filename,'r') as result:
                for line in result:
                    if re.findall("EventDefinition", line):
                        l = line.partition(":")[2]
                        data = l.split(",")
                        event_name = data[0].strip()
                        raw_event = data[1].strip()
                        event_group = data[2].strip()
                        event_unit = data[3].strip()
                        default_event = (data[4].strip() == 'True')
                        event_counter = int(data[5].strip())
                        event_definition = EventDefinition(event_name, raw_event, event_group, event_unit, default_event, event_counter)
                        event_definitions[cpu].append(event_definition)
                        if event_group == "Software":
                            event_definition = EventDefinition("Trace-" + event_name, "trace-" + raw_event, "Trace", event_unit,
                                                               default_event, event_counter)
                            event_definitions[cpu].append(event_definition)
                    if re.findall("RoofLineEvents", line):
                        has_roofline_events = True
                        roofline_events[cpu] = {'All': None,
                                                'Flops': None,
                                                'Time': '',
                                                'Memory': None}
                    if has_roofline_events:
                        id, par, l = line.partition(":")
                        if id in ["All", "Flops", "Memory", "Time"]:
                            roofline_events[cpu][id] = [e.strip() for e in l.split(",")]
        except Exception as e:
            raise Exception("Error reading line: \"" + line.strip() + "\"")


def modify_event_definitions(cpu, event_definitions):
    perf_events_location = tools.GlobalData.perf_events
    orig_file = os.path.join(perf_events_location, cpu + ".events")
    fh, abs_path = mkstemp()
    start_edit = True
    with open(abs_path, 'wb') as new_file:
        with open(orig_file, 'rb') as result:
            for line in result:
                line = line.decode()
                match = re.search("EventDefinition", line)
                if match:
                    if start_edit:
                        start_edit = False
                        for definition in event_definitions:
                            event_name = definition.event
                            raw_event = definition.raw_event
                            event_group = definition.event_group
                            event_unit = definition.unit
                            if definition.default:
                                default_event = "True"
                            else:
                                default_event = "False"
                            event_counter = str(definition.event_weight)
                            l = ", ".join(["EventDefinition: " + event_name, raw_event, event_group, event_unit, default_event, event_counter]) + "\n"
                            new_file.write(l.encode())
                else:
                    new_file.write(line.encode())
    os.close(fh)
    os.remove(orig_file)
    move(abs_path, orig_file)


def modify_cpus(cpus):
    perf_events_location = tools.GlobalData.perf_events
    old_cpus = []
    for f in os.listdir(perf_events_location):
        cpu, dot, ext = f.rpartition(".")
        if ext == "events":
            if cpu not in cpus:
                old_cpus.append(cpu)
                filename = os.path.join(perf_events_location, f)
                os.remove(filename)
    for cpu in cpus:
        if cpu not in old_cpus:
            filename = os.path.join(perf_events_location, cpu + ".events")
            open(filename, 'rw')
            os.close(filename)

def get_event_weights():
    return [1, 10, 100, 1000, 10000, 20000, 40000, 80000, 160000, 320000, 640000, 1280000, 2560000, 5120000]


class CpuDefinition:

    def __init__(self, cpu_name, available_events, roofline_events=None):
        self.base_event = "Cycles"
        self.cpu_name = cpu_name
        self.available_events = available_events
        self.active_events = []
        self.roofline_events = roofline_events

    def copy_to_active_event(self, event):
        for event_definition in self.available_events:
            if event_definition.event == event:
                self.active_events.append(event_definition)

    def add_active_event(self, event, raw_event, event_group, unit, default=False, event_weight=0):
        active_events = self.get_active_events()
        if event not in active_events:
            self.active_events.append(EventDefinition(event, raw_event, event_group, unit, default, event_weight))

    def get_event_definitions(self):
        return self.available_events

    def set_default_active_events(self):
        self.active_events = []
        default_raw_events = self.get_default_events(raw_events=True)
        for raw_event in default_raw_events:
            event = raw_event_to_event(raw_event, self)
            self.copy_to_active_event(event)

    def set_active_events(self, raw_events):
        self.active_events = []
        if raw_events:
            available_raw_events = self.get_available_raw_events()
            for raw_event in raw_events:
                if raw_event in available_raw_events:
                    event = raw_event_to_event(raw_event, self)
                    self.copy_to_active_event(event)

    def get_base_event(self):
        return self.base_event

    def get_default_events(self, raw_events=False):
        if raw_events:
            available_event_map = self.get_available_event_map(event_to_raw_event=True)
            return [available_event_map[event_definition.event] for event_definition in self.available_events if event_definition.default]
        else:
            return [event_definition.event for event_definition in self.available_events if event_definition.default]

    def get_available_event_group_map(self):
        return {event_definition.event: event_definition.event_group for event_definition in self.available_events}

    def get_available_raw_events(self):
        return [event_definition.raw_event for event_definition in self.available_events]

    def get_available_events(self):
        return natural_sort([event_definition.event for event_definition in self.available_events])

    def get_available_event_units(self):
        return {event_definition.event: event_definition.unit for event_definition in self.available_events}

    def get_available_event_map(self, event_to_raw_event=True):
        if event_to_raw_event:
            event_map = {event_definition.event: event_definition.raw_event for event_definition in self.available_events}
        else:
            event_map = {event_definition.raw_event: event_definition.event for event_definition in self.available_events}
        return OrderedDict(sorted(event_map.items()))

    def get_active_event_group_map(self):
        return {event_definition.event: event_definition.event_group for event_definition in self.active_events}

    def get_active_raw_events(self):
        return [event_definition.raw_event for event_definition in self.active_events]

    def get_active_events(self):
        return natural_sort([event_definition.event for event_definition in self.active_events])

    def get_active_event_units(self):
        return {event_definition.event: event_definition.unit for event_definition in self.active_events}

    def get_active_event_map(self, event_to_raw_event=True):
        if event_to_raw_event:
            event_map = {event_definition.event: event_definition.raw_event for event_definition in self.active_events}
        else:
            event_map = {event_definition.raw_event: event_definition.event for event_definition in self.active_events}
        return OrderedDict(sorted(event_map.items()))

    def get_custom_events(cpu_definition):
        return [event_definition.event for event_definition in cpu_definition if
                event_definition.event_group == "Custom"]

    def get_num_custom_event_ratios(self):
        return len([event for event in self.get_active_events() if get_event_type(event) == "custom_event_ratio"])

    def get_event_groups(self):
        group_set = {event_definition.event_group for event_definition in self.available_events}
        group_set.add("Custom")
        return sorted(list(group_set))

    def get_event_counters(self, run_duration):
        return {event_definition.event: get_event_counter(run_duration, event_definition) for
                    event_definition in self.available_events}

    def get_perf_event_groups(self, run_duration, max_events_per_group, fixed_counter=False, count=0):
        active_events = self.get_active_events()
        available_events = self.get_available_events()
        available_event_map = self.get_available_event_map()
        inverse_map = self.get_available_event_map(event_to_raw_event=False)
        event_group_map = self.get_available_event_group_map()
        event_counters = self.get_event_counters(run_duration)
        event_units = self.get_available_event_units()
        if fixed_counter:
            active_event_counters = {event: count for event in available_events if
                                     event in active_events}
        else:
            active_event_counters = {event: event_counters[event] for event in available_events if event in active_events}
        perf_event_groups = []
        trace_events = []
        for event, counter in sorted(active_event_counters.items(), key=operator.itemgetter(1)):
            if event_group_map[event] == "Trace":
                raw_event = available_event_map[event]
                trace_events.append(raw_event)
        if len(trace_events) > 0:
            if "trace-cpu-clock" in trace_events:
                trace_event = "trace-cpu-clock"
            elif "trace-task-clock" in active_event_counters:
                trace_event = "trace-task-clock"
            else:
                trace_event = trace_events[0]
            ordered_trace_events = [trace_event] + [event for event in trace_events if event != trace_event]
            trace_counter = active_event_counters[inverse_map[trace_event]]
            group = {"flag": "-F", "events": ordered_trace_events, "event_counter": trace_counter, "event_type": "Trace"}
            perf_event_groups.append(copy.deepcopy(group))
        group = {"flag": "-F", "events": [], "event_counter": 0, "event_type": "Standard"}
        n = 0
        for event, counter in sorted(active_event_counters.items(), key=operator.itemgetter(1)):
            raw_event = available_event_map[event]
            event_unit = event_units[event]
            if event_unit == "Hz":
                if event_group_map[event] == "Trace":
                    continue
                if n < max_events_per_group and (fixed_counter or group["event_counter"] == counter):
                    group["events"].append(raw_event)
                    group["event_counter"] = counter
                    n += 1
                else:
                    if n > 0:
                        perf_event_groups.append(copy.deepcopy(group))
                    group = {"flag": "-F", "events": [raw_event], "event_counter": counter, "event_type": "Standard"}
                    n = 1
        if n > 0:
            perf_event_groups.append(copy.deepcopy(group))
        group = {"flag": "-c", "events": [], "event_counter": 0, "event_type": "Standard"}
        n = 0
        for event, counter in sorted(active_event_counters.items(), key=operator.itemgetter(1)):
            raw_event = available_event_map[event]
            event_unit = event_units[event]
            if event_unit == "Samples":
                if event_group_map[event] == "Trace":
                    continue
                if n < max_events_per_group and (fixed_counter or group["event_counter"] == counter):
                    group["events"].append(raw_event)
                    group["event_counter"] = counter
                    n += 1
                else:
                    if n > 0:
                        perf_event_groups.append(copy.deepcopy(group))
                    group = {"flag": "-c", "events": [raw_event], "event_counter": counter, "event_type": "Standard"}
                    n = 1
        if n > 0:
            perf_event_groups.append(copy.deepcopy(group))
        return perf_event_groups

    def trace(self):
        active_events = self.get_active_events()
        event_group_map = self.get_active_event_group_map()
        run_trace = False
        for event in active_events:
            if event_group_map[event] == "Trace":
                run_trace = True
        return run_trace

    def get_enabled_modes(self):
        trace_enabled = False
        roofline_anaylsis_enabled = False
        active_raw_events = self.get_active_raw_events()
        active_events = self.get_active_events()
        event_group_map = self.get_active_event_group_map()
        for event in active_events:
            if event_group_map[event] == "Trace":
                trace_enabled = True
        if self.roofline_events:
            loads = set(self.roofline_events["Memory"]).intersection(set(active_raw_events))
            flops = set(self.roofline_events["Flops"]).intersection(set(active_raw_events))
            time = set(self.roofline_events["Time"]).intersection(set(active_raw_events))
            roofline_anaylsis_enabled = (len(loads) > 0 and len(flops) > 0 and len(time) > 0)
        general_analysis_enabled = len(self.get_active_raw_events()) > 1 and self.base_event in active_events
        return {"roofline_analysis": roofline_anaylsis_enabled,
                "general_analysis": general_analysis_enabled,
                "trace": trace_enabled}


def get_available_cpus():
    available_cpus = [cpu for cpu in event_definitions]
    return available_cpus

def get_default_cpu():
    return "General"

def get_cpu_definition(cpu, raw_events = None):
    if cpu in roofline_events:
        cpu_definition = CpuDefinition(cpu, event_definitions[cpu], roofline_events[cpu])
    else:
        cpu_definition = CpuDefinition(cpu, event_definitions[cpu])
    if raw_events:
        add_custom_events_to_active_events(cpu_definition, raw_events)
    return cpu_definition

def get_time_interval(run_duration):
    if run_duration != "":
        total_time = float(run_duration)
# About 60 time intervals - use total_time (in minutes) to set dt (in seconds)
        return float('{0:0.1f}'.format(total_time))

def get_event_counter(run_duration, event_definition=None):
    if run_duration != "":
        total_time = float(run_duration)
        if event_definition:
            if event_definition.unit == "Samples":
                counter = int(round_sig(float(event_definition.event_weight) * total_time, 4))
                return max(counter, 1)
            else: # Hz
                return tools.GlobalData.user_settings["frequency"]
        else:
# About 3,000 samples for cycles event in each time interval (based on 3 GHz cpu)
            return int(round_sig(1000000.0*total_time, 4))



