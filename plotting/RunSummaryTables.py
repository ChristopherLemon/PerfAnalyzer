from tools.Utilities import round_sig
from tools.CustomEvents import raw_event_to_event
import operator


def generate_run_summary_table(cpu_definition, event_counters, run_numbers, run_durations, run_parameters):
    """Return raw html table with run summary data"""
    table_html = []
    for job in event_counters:
        table_html.append("<table>")
        table_html.append("<thead>")
        table_html.append("<tr>")
        table_html += ["<th>" + job + " Events" "</th>", "<th>Perf Event</th>", "<th>Events Per Sample</th>",
                       "<th>Run Number</th>", "<th>Run Duration (S)</th>", "<th>CPU</th>",
                       "<th>System Wide Profiling</th>", "<th>Time Interval (S)</th>"]
        table_html.append("</tr>")
        table_html.append("</thead>")
        runs = sorted(run_numbers[job].items(), key=operator.itemgetter(1))
        for raw_event, run_number in runs:
            if run_number in run_durations[job]:
                event = raw_event_to_event(raw_event, cpu_definition)
                table_html.append("<tr>")
                table_html.append("<td>" + event + "</td>")
                table_html.append("<td>" + raw_event + "</td>")
                table_html.append("<td>" + str(event_counters[job][raw_event]) + "</td>")
                table_html.append("<td>" + str(run_numbers[job][raw_event]) + "</td>")
                max_run_duration = max(run_durations[job].values())
                pc = round_sig(100.0 * run_durations[job][str(run_number)] / max_run_duration, 2)
                table_html.append("<td>" + str(run_durations[job][str(run_number)]) + " (" + str(pc) + " %)" + "</td>")
                table_html.append("<td>" + str(run_parameters[job]["cpu_id"]) + "</td>")
                if run_parameters[job]["system_wide"]:
                    system_wide_profiling = "YES"
                else:
                    system_wide_profiling = "NO"
                table_html.append("<td>" + system_wide_profiling + "</td>")
                table_html.append("<td>" + str(run_parameters[job]["time_interval"]) + "</td>")
                table_html.append("</tr>")
        table_html.append("</table>")
        table_html.append("<br></br>")
    return "".join(table_html)
