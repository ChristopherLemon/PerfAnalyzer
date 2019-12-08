import logging


def setup_main_logger(log_stream, logfile, logger_name, debug=False):
    """Main logger for home page. Includes stream for HTML output"""
    if debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logger = logging.getLogger(logger_name)
    formatter = logging.Formatter(
        "%(processName)s %(threadName)s %(asctime)s : %(message)s"
    )
    filehandler = logging.FileHandler(logfile, mode="w")
    filehandler.setFormatter(formatter)
    filehandler.setLevel(level)
    streamhandler = logging.StreamHandler()
    streamhandler.setFormatter(formatter)
    streamhandler.setLevel(level)
    htmlformatter = logging.Formatter("%(message)s")
    htmlstreamhandler = logging.StreamHandler(stream=log_stream)
    htmlstreamhandler.setFormatter(htmlformatter)
    htmlstreamhandler.setLevel(level=logging.INFO)
    logger.setLevel(level)
    logger.addHandler(filehandler)
    logger.addHandler(streamhandler)
    logger.addHandler(htmlstreamhandler)


def setup_basic_logger(logger_name, log_file, debug=False):
    """Basic logger for output to log file"""
    if debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logger = logging.getLogger(logger_name)
    formatter = logging.Formatter(
        "%(processName)s %(threadName)s %(asctime)s : %(message)s"
    )
    filehandler = logging.FileHandler(log_file, mode="w")
    filehandler.setFormatter(formatter)
    streamhandler = logging.StreamHandler()
    streamhandler.setFormatter(formatter)
    logger.setLevel(level)
    streamhandler.setLevel(logging.DEBUG)
    logger.addHandler(filehandler)
    logger.addHandler(streamhandler)
