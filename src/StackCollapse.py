# Python version of stack collapse script transcribed from flamegraph.pl by Brendan Gregg.

from collections import defaultdict, Set
import argparse
import re


include_pid = False
include_tid = False
dt = 1.0
nt = 0
accumulate = False
trace_event = ""
output_file = ""
multiplier = 1
order = defaultdict(list)
collapsed = defaultdict(dict)
previous_stacks = defaultdict(lambda: "")
samples = defaultdict(lambda: "")
event_sample = defaultdict(lambda: "")
trace_buffer = []
files = set()
stack = []
time = 0.0
previous_time = 0.0
start_time = -1.0


def remember_stack(primary_event, stack, count):
    if stack not in collapsed[primary_event]:
        order[primary_event].append(stack)
        collapsed[primary_event][stack] = 0
    collapsed[primary_event][stack] += count


def record_trace(primary_event, stack, exe_name, pid, tid, elapsed_time):
    global samples
    global previous_stacks
    global trace_buffer
    global event_sample
    if primary_event == trace_event:
        unique_id = pid + "-" + tid
        if previous_stacks[unique_id] == stack:
            samples[unique_id] += " " + str(elapsed_time)
        else:
            last_trace = previous_stacks[unique_id] + " " + str(samples[unique_id])
            trace_buffer.append(last_trace)
            dump_trace()
            samples[unique_id] = str(elapsed_time)
            previous_stacks[unique_id] = stack
    else:
        unique_id = exe_name + "-" + pid + "/" + tid + ":" + primary_event
        event_sample[unique_id] += " " + str(elapsed_time)


def dump_trace(finalise=False):
    global trace_buffer
    global files
    global trace_buffer
    global event_sample
    if (len(trace_buffer) > 100 or finalise):
        filename = output_file + "_trace-" + trace_event
        if filename in files:
            f = open(filename, 'ab')
        else:
            files.add(filename)
            f = open(filename, 'wb')
            l = "start-time;" + str(start_time) + "\n"
            f.write(l.encode())
        for val in trace_buffer:
            l = val + "\n"
            f.write(l.encode())
        for unique_id in event_sample:
            l = "secondary-event;" + unique_id + ":" + event_sample[unique_id] + "\n"
            f.write(l.encode())
        f.close()
        trace_buffer = []
        event_sample = defaultdict(lambda: "")


def dump_stacks():
    global telapsed
    global files
    global collapsed
    global nt
    global order
    telapsed = time - start_time
    for event in collapsed:
        filename = output_file + "_" + event
        if filename in files:
            f = open(filename, 'ab')
        else:
            files.add(filename)
            f = open(filename, 'wb')
            l = "start-time;" + str(start_time) + "\n"
            f.write(l.encode())
        l = "t=" + '{:.2f}'.format(float(nt)*float(dt)) + "\n"
        f.write(l.encode())
        for k in order[event]:
            l = k + " " + str(collapsed[event][k]) + "\n"
            f.write(l.encode())
        f.close()
    nt += 1
    collapsed = defaultdict(dict)
    order = defaultdict(list)


def finalise():
    global telapsed
    for filename in files:
        telapsed = time - start_time
        f = open(filename, 'ab')
        l = "t=" + '{:.2f}'.format(telapsed)
        f.write(l.encode())
        f.close()


def collapse_stacks(input_file):
    global time
    global start_time
    global previous_time
    stack = []
    primary_event = ""
    pid = ""
    tid = ""
    cid = ""
    with open(input_file) as f:
        for line in f:
            if line[0] == "#":
                continue
            line = line.strip()
            if len(line) == 0:
                if pname:
                    stack.append(pname)
                else:
                    stack.append("")
                if trace_event != "":
                    record_trace(primary_event, ";".join(stack[::-1]), exe_name, pid, tid, time - start_time)
                else:
                    remember_stack(primary_event, ";".join(stack[::-1]), int(period))
                if accumulate:
                    stack[-1] = pname_sum_threads
                    if trace_event != "":
                        record_trace(primary_event, ";".join(stack[::-1]), exe_name, pid, "all", time - start_time)
                    else:
                        remember_stack(primary_event, ";".join(stack[::-1]), int(period))
                    stack[-1] = pname_sum_processes
                    if trace_event != "":
                        record_trace(primary_event, ";".join(stack[::-1]), exe_name, "all", "all", time - start_time)
                    else:
                        remember_stack(primary_event, ";".join(stack[::-1]), int(period))
                stack = []
                pname = ""
                pname_sum_threads = ""
                pname_sum_processes = ""
                continue
            # match time stamp int.int:
            match = re.match(".*\s+(\d+\.\d+):.*", line)
            if match:
                time = float(match.group(1))
                if start_time < 0:
                    start_time = time
                    previous_time = time
                elif time - previous_time > dt:
                    previous_time = time
                    dump_stacks()
            # match core number [int] and strip leading zeros
            match = re.match(".*\s+\[(\d+)\]\s+.*", line)
            if match:
                cid = match.group(1)
                cid = re.sub("^0+", "", cid)
                if cid == "":
                    cid = "0"
            # match start of event sample
            # exe ... pid/tid ... time: ... (period?) ... event: ...
            match = re.match("^(\S.+?)\s+(\d+)\/*(\d+)*\s+([^:]+):\s*(?:(\d+)\s+)?([^\s]+):\s*", line)
            if match:
                exe_name = match.group(1)
                primary_event = match.group(6)
                if match.group(5):
                    period = match.group(5)
                else:
                    period = multiplier
                if match.group(3):
                    pid = match.group(2)
                    tid = match.group(3)
                else:
                    pid = "?"
                    tid = match.group(2)
                #for system wide mode accumulate sum over physical cpus
                if accumulate and cid != "":
                    pid = cid
                if include_tid:
                    pname = match.group(1) + "-" + pid + "/" + tid
                    pname_sum_threads = match.group(1) + "-" + pid + "/all"
                    pname_sum_processes = match.group(1) + "-all/all"
                elif include_pid:
                    pname = match.group(1) + "-" + pid
                else:
                    pname = match.group(1)
                    pname = pname.replace(" ","_")
            else:
                # match line in call stack
                match = re.match("^\s*(\w+)\s*(.+) \((\S*)\)", line)
                if match:
                    raw_func = match.group(2)
                    mod = match.group(3)
                    if re.match("^\(", raw_func):
                        next
                    inline = []
                    parts = re.split("[\\->]",raw_func)
                    for func in parts:
                        if func == "[unknown]" and mod != "[unknown]":
                            func = mod
                            func = re.sub(".*\/", "", func)
                            func = "[" + func + "]"
                        func = func.replace(";", ":")
                        func = re.sub("[<>\"\']", "", func).replace("\\", "")
                        inline.append(func)
                    stack = inline + stack
                else:
                    print("unrecognised line: " + line)
    dump_stacks()
    if trace_event != "":
        dump_trace(finalise=True)
    finalise()


if __name__ == "__main__":
    """Simplified stack collapse script, based on stackcollapse.pl by Brendan Gregg"""
    parser = argparse.ArgumentParser(description='Perf Profiler')
    parser.add_argument('-pid', '--pid', action="store_true", default=False,  dest="include_pid", help="include pid with process names")
    parser.add_argument('-tid', '--tid', action="store_true", default=False,  dest="include_tid", help="include tid and pid with process names")
    parser.add_argument('-dt', '--dt', type=float, dest="dt", help="time interval (s) of sample bins")
    parser.add_argument('-accumulate', '--accumulate', action="store_true", default=False, dest="accumulate",
                        help="Accumulate totals per process")
    parser.add_argument('-trace_event', '--trace_event', default="", dest="trace_event",
                        help="Trace an event to create a timeline")
    parser.add_argument('-output_file', '--output_file', default="", dest="output_file",
                        help="Common root name of output file")
    parser.add_argument('-input_file', '--input_file', default="", dest="input_file",
                        help="Input perf stacks file")
    parser.add_argument('-muliplier', '--multiplier', type=int, default=1, dest="multiplier",
                        help="Integer multiplier for event counts")
    args = parser.parse_args()
    include_pid = args.include_pid
    include_tid = args.include_tid
    dt = args.dt
    accumulate = args.accumulate
    trace_event = args.trace_event
    input_file = args.input_file
    output_file = args.output_file
    multiplier = args.multiplier
    collapse_stacks(input_file)

    