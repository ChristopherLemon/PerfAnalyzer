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
