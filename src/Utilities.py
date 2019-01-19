import re
import os
import time
import datetime
from math import log10, floor
from decimal import Decimal


def get_datetime():
    """Return current datetime"""
    return datetime.datetime.now()


def get_datetime_diff(datetime1, datetime2):
    """Return time difference between two datetimes"""
    delta = datetime1 - datetime2
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return '%d:%02d:%02d:%02d' % (days, hours, minutes, seconds)


def get_datetime_end(date_time, time_delta):
    """Return end time from datetime and delta datetime"""
    return date_time + time_delta


def timestamp(filename):
    """Time stamp file to prevent browser file caching"""
    dt_stamp = time.strftime("%Y%m%d%H%M%S")
    f, par, ext = filename.partition(".")
    new_filename = f + dt_stamp + par + ext
    return new_filename


def purge(directory, *args):
    """Remove files from directory matching specified pattern"""
    for f in os.listdir(directory):
        for pattern in args:
            if re.search(pattern, f):
                os.remove(os.path.join(directory, f))


def natural_sort(l, key=lambda x: x):
    """natural sort algorithm for alphanumeric strings"""
    def convert(text): return int(text) if text.isdigit() else text

    def alphanum_key(element): return [convert(c) for c in re.split('([0-9]+)', key(element))]
    lns = sorted(l, key=alphanum_key)
    return lns


def round_sig(x, sig=2):
    """Round floating point number to the specified number of significnat digits"""
    if x > 0.0:
        return round(x, sig - int(floor(log10(x))) - 1)
    elif x < 0.0:
        return -round(-x, sig - int(floor(log10(-x))) - 1)
    else:
        return x


def replace_operators(x):
    """Jinja2 filter to replace some html breaking characters"""
    x = re.sub(" ", "", x)
    x = re.sub("/", "div", x)
    x = re.sub("\+", "plus", x)
    return x


def format_percentage(x):
    """Jinja2 filter to tidy up percentages"""
    y = float(x)
    if y >= 100.0:
        return int(100)
    else:
        return x


def format_number(x):
    """Jinja2 context processor to display large numbers using scientific notation"""
    y = float(x)
    if abs(y) >= 1000.0:
        y = '{0:.2E}'.format(Decimal(x))
    else:
        y = str(x)
    return y


def abs_path_to_rel_path(abs_path, start):
    """Jinja2 context processor to get relative path to data folder from template folder"""
    return os.path.relpath(abs_path, start)


def is_float(s):
    """Check if value is float"""
    try:
        float(s)
        return True
    except ValueError:
        return False
