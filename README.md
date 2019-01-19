# PerfAnalyzer

PerfAnalyzer is a browser based performance analysis tool which utilizes Linux perf to monitor hardware event counters, software events, and trace events. The tool originated from a need to analyze codes running on multiple processors and with multiple threads, whilst comparing the performance of different code designs. When combined with the Linux perf events interface, [flamegraphs](http://www.brendangregg.com/flamegraphs.html) proved to be an extremely neat way of visualizing the necessary data. The automation of the job submission process, the data analysis, and the visualization within a web browser, led to the PerfAnalyzer tool.

The tool provides a graphical user interface to handle job submission and visualization of performance profiles using flamegraphs, charts, and tables. These elements are combined with the Flask framework to create highly interactive representations of the data. Databases created by HPCToolKit can also be interpreted, to create loop or source line level flamegraphs, which can then be used to navigate the associated source code.

The PerfAnalyzer tool can be used to monitor all processes and threads of an application, or it can monitor activity on each processor of the underlying system. Jobs can be submitted using the Message Parsing Interface (MPI), queueing systems such as LSF, and SSH. This permits both local and remote profiling of an application, perhaps running on a cluster or a cloud server. Further details can be found in the Wiki



<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/loop.png" width="45%" title="Loop or line level flamegraph linked to source code analysis (using HPCTooKit database)">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/hotspots.png" width="45%" title="Ranked code hotspots">
</p>
<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/source.png" width="45%" title="Loop or line source code analysis (using HPCToolKit database)">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/threads.png" width="45%" title="Control over process and thread selection">
</p>
<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/TraceView.jpg" width="45%" title="Flamegraph of time trace profile">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/TimeLine.jpg" width="45%" title="Event time series">
</p>
<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/diff.png" width="45%" title="Flamegraph difference plot between multiple profiles">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/diffplot.png" width="45%" title="Ranked differences">
</p>
<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/submit_page.png" width="45%" title="Submit perf Jobs, import perf / HPCToolKit data">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/Summary.png" width="45%" title="Run Summary">
</p>

<p>
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/custom.png" width="45%" title="Flamegraph of custom event ratios">
<img src="https://github.com/ChristopherLemon/PerfAnalyzer/blob/master/Wiki/scatter.png" width="45%" title="Crossplots of event data">
</p>

# Setup
Performance data can be gathered for a Linux kernel version of 3.x or later, with the perf package installed and 
sufficient privileges to set /proc/sys/kernel/perf_event_paranoid to a suitable value. It is also possible to use PerfAnalyzer on a Windows system to perform remote profiling of a Linux system. The tool can be run within a Python 3 environment, or can be built with PyInstaller to create a standalone directory, which can then simply be copied to the locations required.  

## Linux Setup
There are some dependencies on cryptograph and lxml, which are required to run within the python environment or to build the standalone version. These can be installed as follows:  

    sudo apt-get install python-lxml  
    sudo apt-get install libxml2-dev libxslt-dev python3-dev  
    sudo apt-get install build-essential libssl-dev libffi-dev python-dev

**Create Python 3 Virtual Environment**

    virtualenv -p python3 perf_analyzer
    source ./perf_analyzer/bin/activate
    pip install -r requirements_linux_py36.txt
    
**Run in Python 3 environment**

    python server.py

**Build redistributable in linux_dist directory**

    pyinstaller --distpath linux_dist server.spec
    
**Run redistributable**

    cd linux_dist/server
    perf_analyzer

The version of Glibc on the build machine should not exceed that on the machines to be run on.

## Windows Setup

**Create Python 3 Virtual Environment**

    virtualenv -p python3 perf_analyzer
    perf_analyzer\Scripts\activate.bat
    pip install -r requirements_py36.txt
    
**Run in Python 3 environment**

    python server.py

**Build redistributable in windows_dist directory**

    pyinstaller --distpath windows_dist server.spec
    
**Run redistributable**

    cd windows_dist\server
    perf_analyzer

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
