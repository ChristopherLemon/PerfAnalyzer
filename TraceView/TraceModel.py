import sys

class TraceModel:

    def __init__(self):
        self.reset()

    def reset(self):
        self.start = 0.0000001
        self.stop = sys.maxsize
        self.reference_id = ""
        self.job = ""
        self.selected_ids = []
        self.flamegraph_type = "cumulative"
        self.process_names = []
        self.jobs = []
        self.system_wide = False
        self.reference_count = 0
        self.layout = self.TraceLayout()

    class TraceLayout(object):
        def __init__(self):
            self.results = None
            self.flamegraph = None
            self.timeline = None
            self.title = None
            self.footer = None
            self.process_filter = None

        def reset(self):
            self.results = None
            self.flamegraph = None
            self.timeline = None
            self.title = None
            self.footer = None
            self.flamegraph_description = None
            self.process_filter = None

        def to_dict(self):
            return vars(self)