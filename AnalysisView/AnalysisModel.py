import sys


class AnalysisModel:

    def __init__(self, analysis_type=None):
        self.reference_id = ""
        self.selected_ids = {}
        self.event = ""
        self.flamegraph_event_type = "original"
        self.analysis_type = analysis_type
        self.append_cluster_labels = False
        self.num_clusters = 11
        self.cluster_labels = []
        self.cluster_events = None
        self.selected_clusters = []
        self.clusters = []
        self.event1 = ""
        self.event2 = ""
        self.xlower = -sys.maxsize
        self.xupper = sys.maxsize
        self.ylower = -sys.maxsize
        self.yupper = sys.maxsize
        self.base_event = ""
        self.process_list = []
        self.process_names = []
        self.flamegraph_mode = "hotspots"
        self.centred_scatter_plot = "default"
        self.reference_event_type = "original"
        self.scatter_plot_type = "hotspots"
        self.log_scale = False
        self.reference_event = ""
        self.reference_process = ""
        self.reference_job = ""
        self.reference_pid = ""
        self.reference_tid = ""
        self.selected_events = []
        self.num_custom_event_ratios = 0
        self.custom_event_ratio = False
        self.text_filter = ""
        self.diff = False
        self.process_names = []
        self.jobs = []
        self.system_wide = False
        self.reference_count = 0
        self.reference_title = ""
        self.layout = self.AnalysisLayout()

    def reset(self, analysis_type=None):
        if analysis_type:
            self.__init__(analysis_type=analysis_type)
        else:
            self.__init__()

    class AnalysisLayout(object):
        def __init__(self):
            self.results = None
            self.flamegraph = None
            self.event_totals_chart = None
            self.event_totals_table = None
            self.event_ratios_chart = None
            self.source_code_table = None
            self.source_code_line = None
            self.text_filter = None
            self.title = None
            self.footer = None
            self.scatter_plot = None
            self.reference_process_ref_id = None
            self.reference_count = None
            self.process_filter = None

        def reset(self):
            self.__init__()

        def to_dict(self):
            return vars(self)
