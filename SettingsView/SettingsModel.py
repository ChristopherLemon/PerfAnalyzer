from src.JobHandler import (
    get_global_mpirun_params,
    get_local_mpirun_params,
    get_perf_params,
    get_lsf_params,
    get_mpirun_appfile,
)


class SettingsModel:
    def __init__(self, set_defaults=True, cpu="General", cpu_definition=None):

        self.build()
        if set_defaults:
            self.set_defaults(cpu, cpu_definition)

    def build(self):
        self.cpu = None
        self.events = None
        self.raw_events = None
        self.dt = None
        self.max_events_per_run = None
        self.proc_attach = None
        self.job_name = None
        self.executable = None
        self.arguments = None
        self.processes = None
        self.processes_per_node = None
        self.global_mpirun_params = None
        self.local_mpirun_params = None
        self.mpirun_version = None
        self.lsf_params = None
        self.perf_params = None
        self.period = None
        self.frequency = None
        self.use_ssh = None
        self.use_lsf = None
        self.use_mpirun = None
        self.run_system_wide = None
        self.run_as_root = None
        self.run_parallel = None
        self.server = None
        self.queue = None
        self.working_directory_linux = None
        self.private_key = None
        self.username = None
        self.password = None
        self.copy_files = None
        self.env_variables = None
        self.bin_path = None
        self.lib_path = None
        self.preload = None

    def set_defaults(self, cpu, cpu_definition):
        self.cpu = cpu
        self.events = cpu_definition.get_active_events()
        self.raw_events = []
        self.dt = 10
        self.max_events_per_run = 4
        self.proc_attach = 1
        self.job_name = ""
        self.executable = ""
        self.arguments = ""
        self.processes = 1
        self.processes_per_node = 1
        self.global_mpirun_params = get_global_mpirun_params()
        self.local_mpirun_params = get_local_mpirun_params()
        self.mpirun_version = get_mpirun_appfile()
        self.lsf_params = get_lsf_params()
        self.perf_params = get_perf_params(False)
        self.period = 5000000
        self.frequency = 199
        self.use_ssh = True
        self.use_lsf = True
        self.use_mpirun = True
        self.run_system_wide = False
        self.run_as_root = False
        self.run_parallel = False
        self.server = ""
        self.queue = ""
        self.working_directory_linux = ""
        self.private_key = ""
        self.username = ""
        self.password = ""
        self.copy_files = ""
        self.env_variables = ""
        self.bin_path = ""
        self.lib_path = ""
        self.preload = ""

    def to_dict(self):
        return vars(self)
