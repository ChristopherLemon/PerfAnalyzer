# PerfAnalyzer

PerfAnalyzer is a lightweight browser based tool for analyzing code performance. The tool can utilize the Linux perf  
hardware event counters and trace events to provide a wealth of information about the performance characteristics of the code. 

The PerfAnalyzer tool is designed for use with high performance codes: it can monitor all processes and 
threads of an application, or it can monitor activity on each processor of the underlying system. Jobs can be submitted 
using the Message Parsing Interface (MPI), queueing systems such as LSF, and SSH. This permits both local and
remote profiling of an application, perhaps running on a cluster or a cloud server.

The browser based interface can submit jobs, and display the results using a number of graphical tools and libraries
(such as flamegraphs and pygal). These elements are combined with the Flask framework to create highly interactive
representations of the performance data.

Performance data can be gathered for a Linux kernel version of 3.x or later, with the perf package installed and 
sufficient privileges to set the /proc/sys/kernel/perf_event_paranoid value to a suitable value (preferably to -1 or 0). 
Performance data can only be gathered on a Linux system, due to the dependency on the perf interface, but the tool
can still be used on a Windows system to conveniently perform remote profiling of a Linux system.
The Python environment required to run PerfAnalyzer on Windows or Linux systems, for Python 2.x or Python 3.x is 
contained in the relevant requirements files. The PyInstaller spec files also allow the creation of a standalone
directory from which the tool can be run on Windows or Linux. See the build_instructions.txt file for further
information.