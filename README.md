# PerfAnalyzer

PerfAnalyzer is a lightweight browser based tool for analyzing code performance. The tool can utilize the Linux perf  
hardware event counters and trace events to provide a wealth of information about the performance characteristics of the code. 

The PerfAnalyzer tool is designed for use with high performance codes: it can monitor all processes and 
threads of an application, or it can monitor activity on each processor of the underlying system. Jobs can be submitted 
using the Message Parsing Interface (MPI), queueing systems, such as LSF, and SSH, allowing use with 
in a wide variety of situations: for local profiling or remote profiling, such as on a cluster or cloud server.

The browser based interface can submit jobs, and display the results using a number of graphical tools and libraries
(such as flamegraphs and pygal). These elements are combined with the Flask framework to create highly interactive
representations of the performance data.

The Linux perf interface requires a linux kernel version 3.x or later. 
Performance data can only be gathered on a Linux system, due to the dependency on the perf interface, but the tool
can still be used on a Windows system to conveniently perform remote profiling of a Linux system.
The Python environment required to run PerfAnalyzer on Windows or Linux systems, for Python 2.x or Python 3.x is 
contained in the relevant requirements files. The Pyinstaller spec files also allow the creation of a standalone
directory from which the tool can be run on Windows or Linux. See the build_instructions.txt file for further
information.