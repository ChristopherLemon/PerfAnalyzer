import logging

def setup_main_logger(log_stream, logfile, logger_name, debug=False):
    if debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
    l = logging.getLogger(logger_name)
    formatter = logging.Formatter('%(processName)s %(threadName)s %(asctime)s : %(message)s')
    filehandler = logging.FileHandler(logfile, mode='w')
    filehandler.setFormatter(formatter)
    filehandler.setLevel(level)
    streamhandler = logging.StreamHandler()
    streamhandler.setFormatter(formatter)
    streamhandler.setLevel(level)
    htmlformatter = logging.Formatter('%(message)s')
    htmlstreamhandler = logging.StreamHandler(stream=log_stream)
    htmlstreamhandler.setFormatter(htmlformatter)
    htmlstreamhandler.setLevel(level=logging.INFO)
    l.setLevel(level)
    l.addHandler(filehandler)
    l.addHandler(streamhandler)
    l.addHandler(htmlstreamhandler)

def setup_basic_logger(logger_name, log_file, debug=False):
    if debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
    l = logging.getLogger(logger_name)
    formatter = logging.Formatter('%(processName)s %(threadName)s %(asctime)s : %(message)s')
    fileHandler = logging.FileHandler(log_file, mode='w')
    fileHandler.setFormatter(formatter)
    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(formatter)
    l.setLevel(level)
    streamHandler.setLevel(logging.DEBUG)
    l.addHandler(fileHandler)
    l.addHandler(streamHandler)
