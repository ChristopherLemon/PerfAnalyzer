import os

from src.Utilities import round_sig


def get_lines(frame, hpc_results):
    frames = hpc_results.get_frames()
    if frame in frames:
        info = frames[frame]
        file = os.path.join(hpc_results.results_dir, info[0])
        line_num = int(info[1])
        text = {"lines": [], "focus": line_num}
        if os.path.isfile(file):
            with open(file) as f:
                for line in f.readlines():
                    text["lines"].append(line)
        else:
            text = {"lines": ["No Data"], "focus": 0}
    else:
        text = {"lines": ["No Data"], "focus": 0}
    return text


def get_file_analysis(stacks_data, process_id, frame, hpc_results):
    frames = hpc_results.get_frames()
    if frame in frames:
        info = frames[frame]
    else:
        return {}, {}
    file_map = hpc_results.get_file_map(stacks_data, process_id)
    current_file = os.path.join(hpc_results.results_dir, info[0])
    if current_file in file_map:
        file_frames = file_map[current_file]
    else:
        file_frames = {}
    inclusive_counts = {}
    exclusive_counts = {}
    for file_frame in file_frames:
        if file_frame in frames:
            info = frames[file_frame]
            line_num = int(info[1])
            inclusive_counts[line_num] = \
                hpc_results.get_inclusive_value(stacks_data, process_id, file_frame)
            exclusive_counts[line_num] = \
                hpc_results.get_exclusive_value(stacks_data, process_id, file_frame)
    return inclusive_counts, exclusive_counts


def get_percentage(count, total):
    if total > 0:
        return 100.0 * float(count) / float(total)
    else:
        return 0.0


def generate_empty_table():
    table_html = ["<table>", "<thead>", "<tr>"]
    table_html += ["<th>Inclusive</th>", "<th>Exclusive</th>", "<th>Line</th>", "<th>Source Code</th>"]
    table_html.append("</tr>")
    table_html.append("</thead>")
    table_html.append("<tr bgcolor=\"white\">")
    table_html.append("<td>" + str(1).ljust(5) + ": " + "</td>")
    table_html.append("<td><pre> No Data </pre></td>")
    table_html.append("<td> - </td>")
    table_html.append("<td> - </td>")
    table_html.append("</tr>")
    table_html.append("</table>")
    info_html = ["<table>"]
    info_html.append("<tr bgcolor=\"white\">")
    info_html.append("<td>" + str(1).ljust(5) + ": " + "</td>")
    info_html.append("<td><pre> No Data </pre></td>")
    info_html.append("</tr>")
    info_html.append("</table>")
    table = "".join(table_html)
    info = "".join(info_html)
    return table, "0", info


def generate_source_code_table(stacks_data, process_id, frame, hpc_results):
    source_lines = get_lines(frame, hpc_results)
    inclusive_counts, exclusive_counts = get_file_analysis(stacks_data, process_id, frame, hpc_results)
    total = hpc_results.get_total_value(stacks_data, process_id)
    table_html = ["<table>", "<thead>", "<tr>"]
    if process_id.event_type == "original":
        table_html += ["<th>Inclusive</th>", "<th>Exclusive</th>", "<th>Line</th>", "<th>Source Code</th>"]
    else:
        table_html += ["<th>Inclusive</th>", "<th>Exclusive</th>", "<th>Line</th>", "<th>Source Code</th>"]
    table_html.append("</tr>")
    table_html.append("</thead>")
    max_len = 1
    for line in source_lines["lines"]:
        max_len = max(max_len, len(line))
    line_num = 0
    for line in source_lines["lines"]:
        line_num += 1
        if inclusive_counts and line_num in inclusive_counts:
            inc = str(inclusive_counts[line_num])
            exc = str(exclusive_counts[line_num])
            if process_id.event_type == "original":
                pc_inc = str(round_sig(get_percentage(inclusive_counts[line_num], total), 4))
                pc_exc = str(round_sig(get_percentage(exclusive_counts[line_num], total), 4))
            else:
                pc_inc = "-"
                pc_exc = "-"
            inc_str = "{} ({}%)".format(inc, pc_inc)
            exc_str = "{} ({}%)".format(exc, pc_exc)
        else:
            inc_str = "-"
            exc_str = "-"
        if line_num == source_lines["focus"]:
            table_html.append("<tr bgcolor=\"grey\">")
        else:
            table_html.append("<tr bgcolor=\"white\">")
        table_html.append("<td>" + inc_str.ljust(20)  + "</td>")
        table_html.append("<td>" + exc_str.ljust(20)  + "</td>")
        table_html.append("<td>" + str(line_num).ljust(5) + ": " + "</td>")
        src = line.rstrip().replace("&", "&amp;").replace("<", "&lt").replace(">", "&gt")
        table_html.append("<td><pre>" + src.ljust(max_len) + "</pre></td>")
        table_html.append("</tr>")
    table_html.append("</table>")
    table = "".join(table_html)
    return table, source_lines["focus"]


def generate_source_code_info(stacks_data, process_id, frame, hpc_results):
    source_lines = get_lines(frame, hpc_results)
    frames = hpc_results.get_frames()
    total = hpc_results.get_total_value(stacks_data, process_id)
    file = ""
    if frame in frames:
        info = frames[frame]
        file = os.path.join(hpc_results.results_dir, info[0])
    table_html = ["<table>", "<thead>", "<tr>"]
    table_html += ["<th>Inclusive</th>", "<th>Exclusive</th>", "<th>Line</th>", "<th>" + file + "</th>"]
    table_html.append("</tr>")
    table_html.append("</thead>")
    max_len = 1
    for line in source_lines["lines"]:
        max_len = max(max_len, len(line))
    line_num = 0
    for line in source_lines["lines"]:
        line_num += 1
        if line_num == source_lines["focus"]:
            inc_val = hpc_results.get_inclusive_value(stacks_data, process_id, frame)
            exc_val = hpc_results.get_exclusive_value(stacks_data, process_id, frame)
            inc = str(inc_val)
            exc = str(exc_val)
            if process_id.event_type == "original":
                pc_inc = str(round_sig(get_percentage(inc_val, total), 4))
                pc_exc = str(round_sig(get_percentage(exc_val, total), 4))
            else:
                pc_inc = "-"
                pc_exc = "-"
            inc_str = "{} ({}%)".format(inc, pc_inc)
            exc_str = "{} ({}%)".format(exc, pc_exc)
            table_html.append("<tr bgcolor=\"grey\">")
        elif -5 <= line_num - source_lines["focus"] <= 250:
            table_html.append("<tr bgcolor=\"white\">")
            inc_str = "-"
            exc_str = "-"
        else:
            continue
        table_html.append("<td>" + inc_str.ljust(20)  + "</td>")
        table_html.append("<td>" + exc_str.ljust(20)  + "</td>")
        table_html.append("<td>" + str(line_num).ljust(5) + ": " + "</td>")
        src = line.rstrip().replace("&", "&amp;").replace("<", "&lt").replace(">", "&gt")
        table_html.append("<td><pre>" + src.ljust(max_len) + "</pre></td>")
        table_html.append("</tr>")
    table_html.append("</table>")
    table = "".join(table_html)
    return table
