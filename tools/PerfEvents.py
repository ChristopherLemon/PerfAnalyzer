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
                              'unit'])

event_definitions = OrderedDict()

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
                        event_definition = EventDefinition(event_name, raw_event, event_group, event_unit)
                        event_definitions[cpu].append(event_definition)
                        if event_group == "Software" or event_name == "Cycles":
                            event_definition = EventDefinition("Trace-" + event_name, "trace-" + raw_event, "Trace", event_unit)
                            event_definitions[cpu].append(event_definition)
        except Exception as e:
            raise Exception("Error reading line: \"" + line.strip() + "\"")


def modify_event_definitions(cpu, event_definitions):
    perf_events_location = tools.GlobalData.perf_events
    orig_file = os.path.join(perf_events_location, cpu + ".events")
    fh, abs_path = mkstemp()
    start_edit = True
    with open(abs_path, 'w') as new_file:
        with open(orig_file, 'r') as result:
            for line in result:
                match = re.search("EventDefinition", line)
                if match:
                    if start_edit:
                        start_edit = False
                        for definition in event_definitions:
                            event_name = definition.event
                            raw_event = definition.raw_event
                            event_group = definition.event_group
                            event_unit = definition.unit
                            if not re.match("Trace", event_name):
                                l = ", ".join(["EventDefinition: " + event_name, raw_event, event_group, event_unit]) + "\n"
                                new_file.write(l)
                else:
                    new_file.write(line)
    os.close(fh)
    os.remove(orig_file)
    move(abs_path, orig_file)


def get_event_weights():
    return [1, 10, 100, 1000, 10000, 20000, 40000, 80000, 160000, 320000, 640000, 1280000, 2560000, 5120000]


class CpuDefinition:

    def __init__(self, cpu_name, available_events):
        self.base_event = "Cycles"
        self.cpu_name = cpu_name
        self.available_events = available_events
        self.active_events = []

    def copy_to_active_event(self, event):
        for event_definition in self.available_events:
            if event_definition.event == event:
                self.active_events.append(event_definition)

    def add_active_event(self, event, raw_event, event_group, unit):
        active_events = self.get_active_events()
        if event not in active_events:
            self.active_events.append(EventDefinition(event, raw_event, event_group, unit))

    def get_event_definitions(self):
        return self.available_events

    def set_default_active_events(self):
        self.active_events = []
        default_raw_events = self.get_default_events()
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

    def get_default_events(self):
        return ["cpu-clock"]

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

    def get_perf_event_groups(self, max_events_per_group, frequency=0, count=0):
        active_events = self.get_active_events()
        available_events = self.get_available_events()
        available_event_map = self.get_available_event_map()
        event_group_map = self.get_available_event_group_map()
        event_units = self.get_available_event_units()
        active_event_counters = {event: frequency for event in available_events if event in active_events}
        perf_event_groups = []
        trace_events = []
        for event, counter in sorted(active_event_counters.items(), key=operator.itemgetter(1)):
            if event_group_map[event] == "Trace":
                raw_event = available_event_map[event]
                trace_events.append(raw_event)
        if len(trace_events) > 0:
            if "trace-cpu-clock" in trace_events:
                trace_event = "trace-cpu-clock"
                trace_flag = "-F"
            elif "trace-task-clock" in active_event_counters:
                trace_event = "trace-task-clock"
                trace_flag = "-F"
            else:
                trace_event = "trace-cycles"
                trace_flag = "-c"
            ordered_trace_events = [trace_event] + [event for event in trace_events if event != trace_event]
            group = {"flag": trace_flag, "events": ordered_trace_events, "event_counter": frequency, "event_type": "Trace"}
            perf_event_groups.append(copy.deepcopy(group))
        group = {"flag": "-F", "events": [], "event_counter": 0, "event_type": "Standard"}
        n = 0
        for event, counter in sorted(active_event_counters.items(), key=operator.itemgetter(1)):
            raw_event = available_event_map[event]
            event_unit = event_units[event]
            if event_unit == "Hz":
                if event_group_map[event] == "Trace":
                    continue
                if n < max_events_per_group:
                    group["events"].append(raw_event)
                    group["event_counter"] = frequency
                    n += 1
                else:
                    if n > 0:
                        perf_event_groups.append(copy.deepcopy(group))
                    group = {"flag": "-F", "events": [raw_event], "event_counter": frequency, "event_type": "Standard"}
                    n = 1
        if n > 0:
            perf_event_groups.append(copy.deepcopy(group))
        group = {"flag": "-c", "events": [], "event_counter": count, "event_type": "Standard"}
        n = 0
        for event, counter in sorted(active_event_counters.items(), key=operator.itemgetter(1)):
            raw_event = available_event_map[event]
            event_unit = event_units[event]
            if event_unit == "Samples":
                if event_group_map[event] == "Trace":
                    continue
                if n < max_events_per_group:
                    group["events"].append(raw_event)
                    group["event_counter"] = count
                    n += 1
                else:
                    if n > 0:
                        perf_event_groups.append(copy.deepcopy(group))
                    group = {"flag": "-c", "events": [raw_event], "event_counter": count, "event_type": "Standard"}
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
        events_enabled = False
        active_events = self.get_active_events()
        event_group_map = self.get_active_event_group_map()
        for event in active_events:
            if event_group_map[event] == "Trace":
                trace_enabled = True
            else:
                events_enabled = True
        general_analysis_enabled = len(self.get_active_raw_events()) > 1 and self.base_event in active_events
        return { "general_analysis": general_analysis_enabled,
                "trace": trace_enabled,
                "events": events_enabled}


def get_available_cpus():
    available_cpus = [cpu for cpu in event_definitions]
    return available_cpus

def get_default_cpu():
    return "General"

def get_cpu_definition(cpu, raw_events = None):
    cpu_definition = CpuDefinition(cpu, event_definitions[cpu])
    if raw_events:
        add_custom_events_to_active_events(cpu_definition, raw_events)
    return cpu_definition




