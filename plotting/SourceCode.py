import os
from tools.Utilities import round_sig


def get_lines(frame, hpc_results):
    frames = hpc_results.get_frames()
    if frame in frames:
        info = frames[frame]
        file = os.path.join(hpc_results.results_dir, info[0])
        line_num = int(info[1])
        text = {"lines": [], "focus": line_num}
        with open(file) as f:
            for line in f.readlines():
                text["lines"].append(line)
    else:
        text = {"lines": ["No Data"], "focus": 0}
    return text


def get_percentages(stacks_data, process_id, frame, hpc_results):
    frames = hpc_results.get_frames()
    if frame in frames:
        info = frames[frame]
    else:
        return {}, {}
    current_file = os.path.join(hpc_results.results_dir, info[0])
    line_counts = {}
    if process_id.event_type == "original":
        x_data = stacks_data.get_original_event_stack_data(process_id)
        total = 0.0
        for stack in x_data:
            node = stack.rpartition(";")[2]
            if node in frames:
                info = frames[node]
                file = os.path.join(hpc_results.results_dir, info[0])
                if file == current_file:
                    count = x_data[stack]
                    line_num = int(info[1])
                    if line_num not in line_counts:
                        line_counts[line_num] = 0
                    line_counts[line_num] += count
            total += float(x_data[stack])
        line_percentages = {}
        for line_num in line_counts:
            line_percentages[line_num] = 100.0 * float(line_counts[line_num]) / total
        return line_percentages, line_counts
    else:
        x_data, y_data = stacks_data.get_custom_event_ratio_stack_data(process_id)
        total = 0.0
        ratios = {}
        for stack in x_data:
            node = stack.rpartition(";")[2]
            if node in frames:
                info = frames[node]
                file = os.path.join(hpc_results.results_dir, info[0])
                if file == current_file:
                    if stack in y_data:
                        count1 = x_data[stack]
                        count2 = y_data[stack]
                        line_num = int(info[1])
                        if float(count1) >= 0.1:
                            ratios[line_num] = float(count2) / float(count1)
                            line_counts[line_num] = count1
            total += float(x_data[stack])
        line_percentages = {}
        for line_num in line_counts:
            line_percentages[line_num] = 100.0 * float(line_counts[line_num]) / total
        return line_percentages, ratios


def generate_empty_table():
    table_html = ["<table>", "<thead>", "<tr>"]
    table_html += ["<th>Line</th>", "<th>Source Code</th>", "<th>Event Count</th>", "<th>Percentage of Total</th>"]
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
    line_percentages, line_counts = get_percentages(stacks_data, process_id, frame, hpc_results)
    table_html = ["<table>", "<thead>", "<tr>"]
    if process_id.event_type == "original":
        table_html += ["<th>Line</th>", "<th>Source Code</th>", "<th>Event Count</th>", "<th>Percentage of Total</th>"]
    else:
        table_html += ["<th>Line</th>", "<th>Source Code</th>", "<th>Event Ratio</th>", "<th>Percentage of Total</th>"]
    table_html.append("</tr>")
    table_html.append("</thead>")
    max_len = 1
    for line in source_lines["lines"]:
        max_len = max(max_len, len(line))
    line_num = 0
    for line in source_lines["lines"]:
        line_num += 1
        if line_percentages and line_num in line_percentages:
            count = str(line_counts[line_num])
            pc = str(round_sig(line_percentages[line_num], 4))
        else:
            count = "-"
            pc = "-"
        if line_num == source_lines["focus"]:
            table_html.append("<tr bgcolor=\"grey\">")
        else:
            table_html.append("<tr bgcolor=\"white\">")
        table_html.append("<td>" + str(line_num).ljust(5) + ": " + "</td>")
        src = line.rstrip().replace("&", "&amp;").replace("<", "&lt").replace(">", "&gt")
        table_html.append("<td><pre>" + src.ljust(max_len) + "</pre></td>")
        table_html.append("<td>" + count.ljust(16) + "</td>")
        table_html.append("<td>" + pc.ljust(5) + "</td>")
        table_html.append("</tr>")
    table_html.append("</table>")
    table = "".join(table_html)
    return table, source_lines["focus"]


def generate_source_code_info(frame, hpc_results):
    source_lines = get_lines(frame, hpc_results)
    table_html = ["<table>"]
    max_len = 1
    for line in source_lines["lines"]:
        max_len = max(max_len, len(line))
    line_num = 0
    for line in source_lines["lines"]:
        line_num += 1
        if line_num == source_lines["focus"]:
            table_html.append("<tr bgcolor=\"grey\">")
        elif abs(line_num - source_lines["focus"]) <= 1:
            table_html.append("<tr bgcolor=\"white\">")
        else:
            continue
        table_html.append("<td>" + str(line_num).ljust(5) + ": " + "</td>")
        src = line.rstrip().replace("&", "&amp;").replace("<", "&lt").replace(">", "&gt")
        table_html.append("<td><pre>" + src.ljust(max_len) + "</pre></td>")
        table_html.append("</tr>")
    table_html.append("</table>")
    table = "".join(table_html)
    return table
