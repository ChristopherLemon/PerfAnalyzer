selected_cpu_definition = None
loaded_cpu_definition = None
hpc_results = []
results_files = []
jobs = []
processes = []
event_group_map = {}
event_groups = {}
results_files = []
available_events = {}
available_settings = {}
job_settings = {}
cpu = ""
local_data = ""
root_directory = ""
perf_events = ""
enabled_modes = {"roofline_analysis": False,
                 "general_analysis": False}
debug = False
n_proc = 4