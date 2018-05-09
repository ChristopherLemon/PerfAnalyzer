from flask import render_template, request, Blueprint, redirect, url_for
import tools.GlobalData
from tools.CustomEvents import get_derived_events, make_custom_event, create_cumulative_count_stack
from EventView.EventView import reset_event_view
from ProcessView.ProcessView import reset_process_view
from AnalysisView.AnalysisView import reset_analysis_view
layout = {}

CustomEventsView = Blueprint('CustomEventsView', __name__, template_folder='templates', static_folder='static')


@CustomEventsView.route('/add_custom_event', methods=['GET', 'POST'])
def add_custom_event():
# Add custom event: sum or ratio of existing events
    global status
    global jobs
    global processes
    status = ""
    layout["Results"] = tools.GlobalData.results_files
    if 'event_ratio_btn' in request.form:
# Force read of modified data
        reset_event_view()
        reset_process_view()
        reset_analysis_view()
        event1 = request.form["event1"]
        event2 = request.form["event2"]
        make_custom_event(tools.GlobalData.loaded_cpu_definition, "ratio", event1, event2)
        custom_event_ratio = event1 + " / " + event2
        status = "Added " + custom_event_ratio
        return redirect(url_for('EventView.event_view', event=custom_event_ratio))
    elif 'event_sum_btn' in request.form:
# Force read of modified data
        reset_event_view()
        reset_process_view()
        reset_analysis_view()
        event1 = request.form["event3"]
        event2 = request.form["event4"]
        make_custom_event(tools.GlobalData.loaded_cpu_definition, "sum", event1, event2)
        custom_event_sum = event1 + " + " + event2
        status = "Added " + custom_event_sum
        return redirect(url_for('EventView.event_view', event=custom_event_sum))
    elif 'derived_event_btn' in request.form:
# Force read of modified data
        reset_event_view()
        reset_process_view()
        reset_analysis_view()
        event1 = request.form["event5"]
        if event1 == "Process-Cumulative-Counts":
            create_cumulative_count_stack(tools.GlobalData.local_data, tools.GlobalData.results_files, output_job_totals=False, output_process_totals=True)
            return redirect(url_for('EventView.event_view', event="Cycles"))
        elif event1 == "Job-Cumulative-Counts":
            create_cumulative_count_stack(tools.GlobalData.local_data, tools.GlobalData.results_files, output_job_totals=True, output_process_totals=False)
            return redirect(url_for('EventView.event_view', event="Cycles"))
        else:
            make_custom_event(tools.GlobalData.loaded_cpu_definition, "derived", event1)
            custom_event_derived = event1
            status = "Added " + custom_event_derived
            return redirect(url_for('EventView.event_view', event=custom_event_derived))
    else:
        layout["title"] = "Create Custom Events " + status
        layout["footer"] = "Loaded Results: " + " & ".join(layout["Results"])
        return render_template('CustomEventsView.html',
                               layout=layout,
                               events=tools.GlobalData.loaded_cpu_definition.get_active_events(),
                               event_group_map=tools.GlobalData.loaded_cpu_definition.get_active_event_group_map(),
                               all_event_groups=tools.GlobalData.loaded_cpu_definition.get_event_groups(),
                               jobs=tools.GlobalData.jobs,
                               processes=tools.GlobalData.processes,
                               enabled_modes=tools.GlobalData.enabled_modes,
                               derived_events=get_derived_events())