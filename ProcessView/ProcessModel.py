

class ProcessModel:

    def __init__(self):
        self.reset()

    def reset(self):
        self.start = 0.0
        self.stop = 0.0
        self.reference_id = ""
        self.selected_ids = []
        self.event = ""
        self.flamegraph_event_type = "original"
        self.custom_event_ratio = False
        self.text_filter = ""
        self.diff = False
        self.flamegraph_type = "plot_for_process"
        self.num_custom_event_ratios = 0
        self.reference_event_type = "original"
        self.reference_process = ""
        self.process_names = []
        self.jobs = []
        self.system_wide = False
        self.reference_count = 0
        self.reference_title = ""
        self.layout = self.ProcessLayout()

    class ProcessLayout(object):
        def __init__(self):
            self.results = None
            self.flamegraph = None
            self.event_totals_chart = None
            self.event_totals_table = None
            self.event_ratios_chart = None
            self.event_time_series = None
            self.event_ratio_time_series = None
            self.title = None
            self.footer = None
            self.process_filter = None

        def reset(self):
            self.results = None
            self.flamegraph = None
            self.event_totals_chart = None
            self.event_totals_table = None
            self.event_ratios_chart = None
            self.event_time_series = None
            self.event_ratio_time_series = None
            self.title = None
            self.footer = None
            self.process_filter = None

        def to_dict(self):
            return vars(self)




