class EventModel:
    def __init__(self):
        self.start = 0.0
        self.stop = 0.0
        self.minval = 0.0
        self.maxval = 0.0
        self.reference_id = ""
        self.selected_ids = []
        self.event = ""
        self.hotspots = 1
        self.custom_event_ratio = False
        self.text_filter = ""
        self.diff = False
        self.exclusive = True
        self.flamegraph_mode = "hotspots"
        self.flamegraph_type = "plot_for_event"
        self.process_names = []
        self.jobs = []
        self.system_wide = False
        self.reference_count = 0
        self.reference_title = ""
        self.layout = self.EventLayout()

    def reset(self):
        self.__init__()

    class EventLayout(object):
        def __init__(self):
            self.results = None
            self.flamegraph = None
            self.event_totals_chart = None
            self.event_totals_table = None
            self.event_totals_chart2 = None
            self.event_totals_table2 = None
            self.event_ratios_chart = None
            self.event_ratios_table = None
            self.source_code_table = None
            self.source_code_info = None
            self.source_code_line = None
            self.min_max_chart = None
            self.min_max_table = None
            self.timechart = None
            self.scatter_plot = None
            self.diff = None
            self.title = None
            self.footer = None
            self.process_filter = None

        def reset(self):
            self.__init__()

        def to_dict(self):
            return vars(self)
