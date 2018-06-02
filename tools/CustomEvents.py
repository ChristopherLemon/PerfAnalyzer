from __future__ import division
import os
import re
import sys
from tempfile import mkstemp
from shutil import move
from os import remove, close
from collections import OrderedDict
from tools.ResultsHandler import get_job_name, get_process_to_event_map

def sort_by_time(data): # For regular time intervals, but possibly with different start/end ranges
    times = []
    sorted_data = OrderedDict()
    for t in data:
        times.append(float(t))
    times.sort()
    for time in times:
        t = '{:.2f}'.format(time)
        stacks = data[t]
        sorted_data[t] = stacks
    return sorted_data

def create_composite_event_stack(stack_data, results_files):
    raw_event = stack_data.event
    for results_file in results_files:
        filenames = ["", ""]
        full_filename = os.path.join(stack_data.path, results_file)
        job = get_job_name(results_file)
        found = get_process_to_event_map(stack_data.path, results_file)
        all_events = []
        for name in found:
            all_events += found[name]
        if raw_event not in all_events:
            for name in found:
                event1, event2 = split_raw_event(raw_event, stack_data.cpu_definition)
                counter1 = get_composite_event_counter(event1, stack_data.event_counters[job])
                counter2 = get_composite_event_counter(event2, stack_data.event_counters[job])
                if is_clock_event(event1) or is_clock_event(event2):
                    # scale1 * counter1 / scale2 * counter2 -> Seconds per event
                    if is_clock_event(event1):
                        scale2 = counter2 * counter1 # multiply event2 counts by event1 frequency (Hz)
                    else:
                        scale2 = 1 # events
                    # scale1 * counter1 / scale2 * counter2 -> events per second
                    if is_clock_event(event2):
                        scale1 = counter1 * counter2 # multiply event1 counts by event2 frequency (Hz)
                    else:
                        scale1 = 1
                    counter = 1
                else:
                    counter = min(counter1, counter2) # lowest common factor
                    scale1 = counter1 // counter
                    scale2 = counter2 // counter
                data = OrderedDict()
                filenames[0] = name + "_" + event1
                filenames[1] = name + "_" + event2
                file0 = os.path.join(stack_data.path, filenames[0])
                file1 = os.path.join(stack_data.path, filenames[1])
                if os.path.isfile(file0) and os.path.isfile(file1):
                    with open(file0, 'r') as infile:
                        t = ""
                        for stack in infile:
                            s = stack.strip()
                            if re.match("t=", s):
                                t = s.partition("=")[2]
                                data[t] = OrderedDict()
                            else:
                                s, par, count = s.rpartition(' ')
                                if s:
                                    data[t][s] = [int(count), 0]
                    file1 = os.path.join(stack_data.path, filenames[1])
                    with open(file1, 'r') as infile:
                        for stack in infile:
                            s = stack.strip()
                            if re.match("t=", s):
                                t = s.partition("=")[2]
                                if t not in data:
                                    data[t] = OrderedDict()
                            else:
                                s, par, count = s.rpartition(' ')
                                if s:
                                    if s in data[t]:
                                        data[t][s][1] = int(count)
                                    else:
                                        data[t][s] = [0, int(count)]
                    ordered_data = sort_by_time(data)
                    custom_event_ratio = bool(re.match(".*-divide-.*", raw_event))
                    if custom_event_ratio:
                        out_file = filenames[0] + "-divide-" + event2
                    else: # sum
                        out_file = filenames[0] + "-plus-" + event2
                    path_to_out_file = os.path.join(stack_data.path, out_file)
                    f = open(path_to_out_file, 'wb')
                    for t in ordered_data:
                        time = "t=" + t + "\n"
                        f.write(time.encode())
                        for stack in ordered_data[t]:
                            if custom_event_ratio:
                                combined_stack = '{} {} {}\n' \
                                    .format(stack, scale1 * ordered_data[t][stack][0], scale2 * ordered_data[t][stack][1])
                                f.write(combined_stack.encode())
                            else: # sum
                                combined_stack = '{} {}\n' \
                                    .format(stack, scale1 * ordered_data[t][stack][0] + scale2 * ordered_data[t][stack][1])
                                f.write(combined_stack.encode())
                    f.close()
                    f_results = open(full_filename, 'a')
                    event_counter_description = "event_counter-" + raw_event + ":run-0:" + str(counter)
                    f_results.write(event_counter_description + "\n")
                    f_results.write(out_file + "\n")
                    f_results.close()


def create_cumulative_count_stack(local_data, results_files, output_job_totals=True, output_process_totals=True):
    for results_file in results_files:
        found = get_process_to_event_map(local_data, results_file)
        process_id_regex = re.compile("((all|[0-9]+)/(all|[0-9]+))")
        events = []
        for name in found:
            events += found[name]
        all_events = {event for event in events} # Remove duplicates
        for found_event in all_events:
            event_type = get_event_type(found_event)
            process_counts = OrderedDict()
            for name in found:
                if name.rpartition("_")[2] == "procall":
                    continue
                for raw_event in found[name]:
                    if raw_event == found_event:
                        thread_counts = OrderedDict()
                        filename = name + "_" + raw_event
                        file = os.path.join(local_data, filename)
                        if os.path.isfile(file):
                            write_process_totals = True
                            with open(file, 'r') as infile:
                                for line in infile:
                                    stack = line.strip()
                                    if line[0:2] == "t=":
                                        t = stack.partition("=")[2]
                                        if t not in thread_counts:
                                            thread_counts[t] = OrderedDict()
                                        if t not in process_counts:
                                            process_counts[t] = OrderedDict()
                                    else:
                                        match = re.search(process_id_regex, line)
                                        if match:
                                            pid = match.group(2)
                                            tid = match.group(3)
                                            if tid == "all": # Skip event if cumulative data already exists
                                                write_process_totals = False
                                            if pid not in thread_counts[t]:
                                                thread_counts[t][pid] = OrderedDict()
                                            stack = line.strip()
                                            if event_type == "custom_event_ratio":
                                                stack, par, secondary = stack.rpartition(' ')
                                            stack, par, primary = stack.rpartition(' ')
                                            if stack:
                                                thread_stack = re.sub("/" + tid, "/all", stack)
                                                process_stack = re.sub(pid + "/", "all/", thread_stack)
                                                if process_stack not in process_counts[t]:
                                                    process_counts[t][process_stack] = [0, 0]
                                                if thread_stack not in thread_counts[t][pid]:
                                                    thread_counts[t][pid][thread_stack] = [0, 0]
                                                thread_counts[t][pid][thread_stack][0] += int(primary)
                                                process_counts[t][process_stack][0] += int(primary)
                                                if event_type == "custom_event_ratio":
                                                    thread_counts[t][pid][thread_stack][1] += int(secondary)
                                                    process_counts[t][process_stack][1] += int(secondary)
                            if output_process_totals and write_process_totals: # Merge thread cumulative data into existing process file
                                fh, abs_path = mkstemp()
                                with open(abs_path, 'wb') as new_file:
                                    with open(file, 'r') as result:
                                        for line in result:
                                            if line[0:2] == "t=":
                                                new_file.write(line.encode())
                                                t = line.strip().partition("=")[2]
                                                if t in thread_counts:
                                                    for pid in thread_counts[t]:
                                                        for stack in thread_counts[t][pid]:
                                                            primary = str(thread_counts[t][pid][stack][0])
                                                            new_line = stack + " " + primary
                                                            if event_type == "custom_event_ratio":
                                                                secondary = str(thread_counts[t][pid][stack][1])
                                                                new_line  += " " + secondary
                                                            new_line += "\n"
                                                            new_file.write(new_line.encode())
                                            else:
                                                new_file.write(line.encode())
                                close(fh)
                                remove(file)
                                move(abs_path, file)
            if output_job_totals:
                out_file = re.sub("proc[0-9]+_", "procall_", filename)
                file = os.path.join(local_data, out_file)
                f = open(file, 'wb') # Write Process cumulative data to new process file
                for t in process_counts:
                    time = "t=" + t + "\n"
                    f.write(time.encode())
                    for stack in process_counts[t]:
                        primary = str(process_counts[t][stack][0])
                        new_line = stack + " " + primary
                        if event_type == "custom_event_ratio":
                            secondary = str(process_counts[t][stack][1])
                            new_line += " " + secondary
                        new_line += "\n"
                        f.write(new_line.encode())
                f.close()
                full_filename = os.path.join(local_data, results_file)
                f_results = open(full_filename, 'a')
                f_results.write(out_file + "\n")
                f_results.close()


derived_events = {"process-cumulative-counts": {"event": "Process-Cumulative-Counts", "unit": "samples"},
                  "job-cumulative-counts": {"event": "Job-Cumulative-Counts", "unit": "samples"}}
derived_event_map = {derived_events[raw_event]["event"]: raw_event for raw_event in derived_events}

def get_derived_events():
    return [event for event in derived_event_map]

def create_custom_event_stack(stack_data, results_files, raw_event):
    if raw_event == "job-cumulative-counts" or raw_event == "process-cumulative-counts":
        return
    elif is_composite_event(raw_event):
        create_composite_event_stack(stack_data, results_files)
    return

def is_derived_event(raw_event):
    return raw_event in derived_events

def is_composite_event(raw_event):
    custom_event = bool(re.match(".*-divide-.*", raw_event))
    custom_event |= bool(re.match(".*-plus-.*", raw_event))
    return custom_event

def is_clock_event(raw_event):
    return re.match(".*clock", raw_event)

def event_to_raw_event(event, cpu_definition):
    # Convert " / " to "-divide-",
    #         " + " to "-plus-",
    #         user event to perf raw_event
    if event in derived_event_map:
        return derived_event_map[event]
    event_map = cpu_definition.get_available_event_map(event_to_raw_event=True)
    r1, par, r2 = event.partition(" / ")
    if r1 != "":
        e1 = "-plus-".join([event_map[e] for e in re.split(" \+ ", r1)])
    if r2 != "":
        e2 = "-plus-".join([event_map[e] for e in re.split(" \+ ", r2)])
        return e1 + "-divide-" + e2
    else:
        return e1


def raw_event_to_event(raw_event, cpu_definition):
# Convert "-divide-" to " / ",
#         "-plus-" to " + ",
#         perf raw_event to user event
    if raw_event in derived_events:
        return derived_events[raw_event]["event"]
    event_map = cpu_definition.get_available_event_map(event_to_raw_event=False)
    r1, par, r2 = raw_event.partition("-divide-")
    if r1 != "":
        e1 = " + ".join([event_map[e] for e in re.split("-plus-", r1)])
    if r2 != "":
        e2 = " + ".join([event_map[e] for e in re.split("-plus-", r2)])
        return e1 + " / " + e2
    else:
        return e1


def get_event_type(event):
    custom_event_ratio = bool(re.match(".*-divide-.*", event))
    custom_event_ratio |= bool(re.match(".* / .*", event))
    if custom_event_ratio:
        event_type = "custom_event_ratio"
    else:
        event_type = "original"
    return event_type

def split_raw_event(raw_event, cpu_definition):
    raw_events = cpu_definition.get_active_raw_events()
    for event1 in raw_events:
        for event2 in raw_events:
            combined_event = event1 + "-divide-" + event2
            if combined_event == raw_event:
                return event1, event2
    for event1 in raw_events:
        for event2 in raw_events:
            combined_event = event1+ "-plus-" + event2
            if combined_event == raw_event:
                return event1, event2
    return raw_event, None

def get_composite_event_counter(raw_event, raw_event_counters):
    c1 = sys.maxsize
    c2 = sys.maxsize
    r1, par, r2 = raw_event.partition("-divide-")
    if r1 != "":
        e1 = [raw_event_counters[e] for e in re.split("-plus-", r1)]
        c1 = min(e1)
    if r2 != "":
        e2 = [raw_event_counters[e] for e in re.split("-plus-", r2)]
        c2 = min(e2)
    min_event_counter = min(c1, c2)
    return min_event_counter

def make_custom_event(cpu_definition, type, event1, event2=None):
    event_map = cpu_definition.get_active_event_map(event_to_raw_event=True)
    units = cpu_definition.get_active_event_units()
    if type == "ratio":
        event = event1 + " / " + event2
        raw_event = event_map[event1] + "-divide-" + event_map[event2]
        event_group = "Custom"
        unit1 = units[event1]
        unit2 = units[event2]
        if unit1 == unit2:
            unit = "Dimensionless"
        else:
            unit = unit1 + " / " + unit2
        cpu_definition.add_active_event(event, raw_event, event_group, unit)
    elif type == "sum":
        event = event1 + " + " + event2
        raw_event = event_map[event1] + "-plus-" + event_map[event2]
        event_group = "Custom"
        unit = units[event1]
        cpu_definition.add_active_event(event, raw_event, event_group, unit)
    elif type == "derived":
        event = event1
        raw_event = derived_event_map[event]
        event_group = "Custom"
        unit = derived_events[raw_event]["unit"]
        cpu_definition.add_active_event(event, raw_event, event_group, unit)


def add_custom_events_to_active_events(cpu_definition, raw_events):
    available_raw_events = cpu_definition.get_available_raw_events()
    found_custom_event_ratio = False
    composite_events = []
    for raw_event in raw_events:
        if raw_event in available_raw_events:
            event = raw_event_to_event(raw_event, cpu_definition)
            cpu_definition.copy_to_active_event(event)
        elif is_derived_event(raw_event):
            event = derived_events[raw_event]["event"]
            make_custom_event(cpu_definition, "derived", event)
        else:
            composite_events.append(raw_event)
    # Deal with sums
    if len(composite_events) > 0:
        active_raw_events = cpu_definition.get_active_raw_events()
        active_event_units = cpu_definition.get_active_event_units()
        for raw_event in composite_events:
            if raw_event not in active_raw_events:
                event_type = get_event_type(raw_event)
                if event_type == "custom_event_ratio":
                    found_custom_event_ratio = True
                else:
                    event = raw_event_to_event(raw_event, cpu_definition)
                    event_group = "Custom"
                    event1, event2 = split_raw_event(raw_event, cpu_definition)
                    event1 = raw_event_to_event(event1, cpu_definition)
                    unit = active_event_units[event1]
                    cpu_definition.add_active_event(event, raw_event, event_group, unit, False, 0)
    # Deal with ratios (possibly of sums)
    if found_custom_event_ratio:
        active_raw_events = cpu_definition.get_active_raw_events()
        active_event_units = cpu_definition.get_active_event_units()
        for raw_event in composite_events:
            if raw_event not in active_raw_events:
                event_type = get_event_type(raw_event)
                if event_type == "custom_event_ratio":
                    event_group = "Custom"
                    event1, event2 = split_raw_event(raw_event, cpu_definition)
                    event = raw_event_to_event(raw_event, cpu_definition)
                    event1 = raw_event_to_event(event1, cpu_definition)
                    event2 = raw_event_to_event(event2, cpu_definition)
                    unit1 = active_event_units[event1]
                    unit2 = active_event_units[event2]
                    if unit1 == unit2:
                        unit = "Dimensionless"
                    else:
                        unit = unit1 + " / " + unit2
                    cpu_definition.add_active_event(event, raw_event, event_group, unit, False, 0)

