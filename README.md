# PerfAnalyzer

PerfAnalyzer is an interactive browser based tool designed for detailed analysis of code performance. The tool utilizes Linux perf hardware event counters and software events, and provides a graphical interface to handle job submission and visualization of performance profiles. Flamegraphs, charts, and tables are used to aid understanding, and these elements are combined with the Flask framework to create highly interactive representations of the performance data. Databases produced by HPCToolKit can also be interpreted, to create loop or source line level flamegraphs dynamically linked with the associated source code.

The PerfAnalyzer tool is designed for use with high performance codes: it can monitor all processes and 
threads of an application, or it can monitor activity on each processor of the underlying system. Jobs can be submitted 
using the Message Parsing Interface (MPI), queueing systems such as LSF, and SSH. This permits both local and
remote profiling of an application, perhaps running on a cluster or a cloud server.



<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/EventView.jpg" width="45%" title="Event FlameGraph">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/EventCounts.jpg" width="45%" title="Event Counts">
</p>
<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/Diff.jpg" width="45%" title="Flamegraph Diff">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/DiffCount.jpg" width="45%" title="Diff Counts">
</p>
<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/TraceView.jpg" width="45%" title="Flamegraph Trace">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/TimeLine.jpg" width="45%" title="Event Time Series">
</p>
<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/Ratio.jpg" width="45%" title="Flamegraph for event ratios">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/Analysis.jpg" width="45%" title="Event Crossplots">
</p>

# Setup
Performance data can be gathered for a Linux kernel version of 3.x or later, with the perf package installed and 
sufficient privileges to set /proc/sys/kernel/perf_event_paranoid to a suitable value. It is also possible to use PerfAnalyzer on a Windows system to perform remote profiling of a Linux system. The tool can be run within a Python environment, or can be built with PyInstaller to create a standalone directory, which can then simply be copied to the locations required.  

## Linux Setup
There are some dependencies on lxml, which are required to run within the python environment or to build the standalone version. These can be installed as follows:  

    sudo apt-get install python-lxml  
    sudo apt-get install libxml2-dev libxslt-dev python-dev  

For python 3, the python3-dev package should be installed instead of python-dev.

**Virtual Environment**
For Python 2

    virtualenv perf_profiler
    source ./perf_profiler/bin/activate
    pip install -r requirements_linux.txt

**Virtual Environment**
For Python 3

    virtualenv -p python3 perf_profiler
    source ./perf_profiler/bin/activate
    pip install -r requirements_linux_py36.txt

**Build redistributable in linux_dist directory**

    pyinstaller --distpath linux_dist server.spec

The version of Glibc on the build machine should not exceed that on the machines to be run on.

## Windows Setup

**Virtual environment**
For Python 2

    virtualenv perf_profiler
    perf_profiler\Scripts\activate.bat
    pip install -r requirements.txt

**Virtual Environment**
For Python 3

    virtualenv -p python3 perf_profiler
    perf_profiler\Scripts\activate.bat
    pip install -r requirements_py36.txt

**Build redistributable in windows_dist directory**

    pyinstaller --distpath windows_dist server.spec

## Perf Setup

If not already installed, perf will need to be installed on the target machine. For Ubuntu: 

    apt-get install linux-tools-common linux-tools-generic linux-tools-`uname -r`

Next the perf_paranoid setting should be set to an appropriate value. Setting it to 0 or -1 provides the required functionality.

    sudo sh -c 'echo -1 >/proc/sys/kernel/perf_event_paranoid'

It may also prove useful to see the origin of kernel calls with

    sudo sh -c 'echo 0 >/proc/sys/kernel/kptr_restrict'
    
## Browser
If no browser is specified the system default browser is used. The recommended browser is Chrome/chromium-browser, which can be passed as an optional command line argument.

    perf_analyzer --browser=/path/to/browser
