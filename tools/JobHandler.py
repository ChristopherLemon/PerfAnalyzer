import io
import os
import re
import shutil
import threading
import subprocess
from tools.CustomLogging import setup_basic_logger
from tools.Utilities import purge
import tools.GlobalData
import paramiko
from paramiko import BadHostKeyException, AuthenticationException, SSHException
import socket
import logging
from tools.ResultsHandler import modify_process_ids, modify_system_wide_process_ids, replace_results_file

def get_lsf_params(lsf_params=None, lib_path=None, preload=None, env_variables=None, bin_path=None):
    if lsf_params:
        env = get_lsf_env(lib_path, preload, env_variables, bin_path)
        command = "{} -env {}".format(lsf_params, env)
    else:
        command = "-K -x -q -R \"span[ptile=1]\" -n 1"
    return command

def get_lsf_env(lib_path, preload, env_variables, bin_path):
    bin_path_env = re.sub(",", ":", bin_path)
    lib_path_env = re.sub(",", ":", lib_path)
    preload_env = re.sub(",", ":", preload)
    env = '\"all'
    if len(lib_path_env) > 0:
        env += ',LD_LIBRARY_PATH={}:$LD_LIBRARY_PATH'.format(lib_path_env)
    if len(preload_env) > 0:
        env += ',LD_PRELOAD={}'.format(preload_env)
    if len(env_variables) > 0:
        env += ',{}'.format(env_variables)
    if len(bin_path_env) > 0:
        env += ',PATH={}:$PATH'.format(bin_path_env)
    env += '\"'
    return env

def get_sudo_command(run_as_root, env_variables=None):
    if not run_as_root:
        return ""
    else:
        vars = []
        for var in env_variables.split(","):
            var_name = var.partition("=")[0]
            vars.append(var_name + "=$" + var_name)
        vars.append("PATH=$PATH")
        vars.append("LD_PRELOAD=$LD_PRELOAD")
        vars.append("LD_LIBRARY_PATH=$LD_LIBRARY_PATH")
        var_string = " ".join(vars)
        return "sudo " + var_string + " "
        #eturn "sudo -E "

def get_global_mpirun_params(params=""):
    return params

def get_local_mpirun_params(params=""):
    return params

def get_mpirun_appfile(mpi_version=None):
    if mpi_version:
        # Intel MPI: -configfile, OpenMPI: -app, Platform MPI: -f
        if re.search("Intel",mpi_version):
            appfile = "-configfile"
        elif re.search("Open",mpi_version):
            appfile = "-app"
        elif re.search("Platform",mpi_version):
            appfile = "-f"
    else:
        appfile = ""
    return appfile

def get_perf_params(system_wide):
    if system_wide:
        command = "perf record --call-graph dwarf -a"
    else:
        command = "perf record --call-graph dwarf"
    return command

def get_remove_old_data_command(job_id, system_wide):
    if system_wide:
        event_files = job_id + "_host*"
    else:
        event_files = job_id + "_proc*"
    command = "rm -f " + event_files + "\n"
    return command

def get_perf_out_file_name(job_id, pid, n_group, system_wide):
    if system_wide:
        perf_out_file = job_id + "_host" + str(pid) + "run" + str(n_group) + ".perf"
    else:
        perf_out_file = job_id + "_proc" + str(pid) + "run" + str(n_group) + ".perf"
    return perf_out_file

def get_perf_script_command(job_id, pid, n_group, system_wide, use_lsf, env, queue, sudo=""):
# For linux 3.x+, since older versions of perf used -f instead of -F"
    if system_wide:
        in_file = job_id + "_host" + str(pid) + "run" + str(n_group) + ".perf"
        out_file = job_id + "_host" + str(pid) + "run" + str(n_group) + ".stacks"
        if use_lsf:
            command = 'bsub -K -env {} -e bjobs.err -o bjobs.out -q {} -n 1 \"{}perf script -F comm,cpu,pid,tid,time,event,ip,sym,dso --show-kernel-path -i {} > {} \" &\n'.format(
            env, queue, sudo, in_file, out_file)
        else:
            command = "{}perf script -F comm,cpu,pid,tid,time,event,ip,sym,dso --show-kernel-path -i {} > {} &\n".format(sudo, in_file, out_file)
    else:
        in_file = job_id + "_proc" + str(pid) + "run" + str(n_group) + ".perf"
        out_file = job_id + "_proc" + str(pid) + "run" + str(n_group) + ".stacks"
        if use_lsf:
            command = 'bsub -K -env {} -e bjobs.err -o bjobs.out -q {} -n 1 \"{}perf script -F comm,pid,tid,time,event,ip,sym,dso --show-kernel-path -i {} > {} \" &\n'.format(
            env, queue, sudo, in_file, out_file)
        else:
            command = "{}perf script -F comm,pid,tid,time,event,ip,sym,dso --show-kernel-path -i {} > {} &\n".format(sudo, in_file, out_file)
    return command

def get_stack_collapse_command(job_id, pid, n_group, dt, stack_collapse_script, system_wide, trace_event=None):
    if system_wide:
        in_file = job_id + "_host" + str(pid) + "run" + str(n_group) + ".stacks"
        out_file = job_id + "_host" + str(pid)
        command = 'cat {} | perl {} --pid --tid --output_file={} --dt={} --accumulate'.format(in_file, stack_collapse_script, out_file, dt)
    else:
        in_file = job_id + "_proc" + str(pid) + "run" + str(n_group) + ".stacks"
        out_file = job_id + "_proc" + str(pid)
        command = 'cat {} | perl {} --pid --tid --output_file={} --dt={}'.format(in_file, stack_collapse_script, out_file, dt)
    if trace_event:
        command += " --trace_event=" + trace_event
    command += " &\n"
    return command

def get_copy_results_command(job_id, results_file, system_wide):
    if system_wide:
        command = "for file in " + job_id + "_host*_*; do echo $file >> " + results_file + "; done\n"
    else:
        command = "for file in " + job_id + "_proc*_*; do echo $file >> " + results_file + "; done\n"
    return command

class JobHandler:

    def __init__(self, job_id, copy_files, run_parallel, run_system_wide, run_as_root, processes,
                 processes_per_node, exe, exe_args, working_dir, root_directory, run_duration,
                 queue, cpu_definition, events, count, frequency, dt, max_events_per_run,
                 proc_attach, env_variables, bin_path, lib_path, preload, global_mpirun_params, local_mpirun_params,
                 mpirun_version, lsf_params, perf_params, use_mpirun, use_lsf, use_ssh):
        self.job_id = job_id
        self.processes = processes
        self.processes_per_node = processes_per_node
        self.exe = exe
        self.exe_args = exe_args
        self.copy_files = re.sub(","," ",copy_files)
        self.run_parallel = run_parallel
        self.system_wide = run_system_wide
        self.run_as_root = run_as_root
        self.working_dir = working_dir
        self.queue = queue
        self.cpu_definition = cpu_definition
        self.cpu = self.cpu_definition.cpu_name
        self.mpi_config_files = []
        self.events = events
        self.count = count
        self.root_directory = root_directory
        if run_duration == "":
            self.run_duration = run_duration
        else:
            self.run_duration = float(run_duration)
        self.fixed_counter = (run_duration == "")
        self.frequency = frequency
        self.dt = dt
        self.proc_attach = proc_attach
        self.env_variables = env_variables
        self.bin_path = re.sub(",", ":", bin_path)
        self.lib_path = re.sub(",", ":", lib_path)
        self.preload = re.sub(",", ":", preload)
        self.lsf_env = get_lsf_env(lib_path, preload, env_variables, bin_path)
        self.sudo_command = get_sudo_command(run_as_root, env_variables)
        self.global_mpirun_params = global_mpirun_params
        self.local_mpirun_params = local_mpirun_params
        self.mpirun_appfile = get_mpirun_appfile(mpirun_version)
        self.lsf_params = get_lsf_params(lsf_params, lib_path, preload, env_variables, bin_path)
        self.perf_params = perf_params
        self.use_mpirun = use_mpirun
        self.use_lsf = use_lsf
        self.use_ssh = use_ssh
        self.max_events_per_run = max_events_per_run
        log_file = os.path.join(tools.GlobalData.local_data, "scriptwriting.log")
        setup_basic_logger('scriptwriting_logger', log_file, debug=tools.GlobalData.debug)
        self.scriptwriting_logger = logging.getLogger("scriptwriting_logger")

    def execute_perf(self, job_settings):
        local_data = tools.GlobalData.local_data
        purge(local_data, job_settings["job_name"] + "_proc")
        purge(local_data, job_settings["job_name"] + "_host")
        purge(local_data, job_settings["job_name"] + ".results")
        purge(local_data, job_settings["job_name"] + ".done")
        self.scriptwriting_logger.info(u" Write perf script")
        stack_collapse_script = 'stackcollapse-perf-modified.pl'
        perf_script = self.write_perf_script(local_data, stack_collapse_script)
        self.scriptwriting_logger.info(u" Setup background threads")
        try:
            background_thread = threading.Thread(target=self.execute_commands, args=(local_data,job_settings,perf_script,stack_collapse_script))
            background_thread.daemon = True
            background_thread.start()
        except Exception as e:
            raise Exception(str(e))

    def execute_command(self, command, client=None, return_output=False):
        if client:
            self.scriptwriting_logger.debug(u" Submitted remote command: " + command)
            stdin, stdout, stderr = client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status > 0:
                self.scriptwriting_logger.error(u" Command error: " + "".join(stderr.readlines()))
            else:
                self.scriptwriting_logger.info(u" Executed command: " + command)
            if return_output:
                return stdout
        else:
            self.scriptwriting_logger.debug(u" Submitted local command: " + command)
            try:
                output = subprocess.check_output(command, shell=True)
            except Exception as e:
                self.scriptwriting_logger.error(u" Command error: " + command + ": " + str(e))
            else:
                self.scriptwriting_logger.info(u" Executed command: " + command)
            if return_output:
                return output

    def get_file(self, remotefile, localfile, stfp=None):
        if stfp:
            self.scriptwriting_logger.info(u" Copying: " + remotefile + " -> " + localfile)
            try:
                stfp.get(remotefile, localfile)
            except Exception as e:
                self.scriptwriting_logger.error(u"" + str(e))
            else:
                self.scriptwriting_logger.info(u" Copy successful")
        else:
            self.scriptwriting_logger.info(u" Copying: " + remotefile + " -> " + localfile)
            try:
                localdir = os.path.dirname(localfile)
                shutil.copy(remotefile, localdir)
            except Exception as e:
                self.scriptwriting_logger.error(u"" + str(e))
            else:
                self.scriptwriting_logger.info(u" Copy successful")

    def put_file(self, localfile, remotefile, stfp=None):
        if stfp:
            self.scriptwriting_logger.info(u" Copying: " + localfile + " -> " + remotefile)
            try:
                stfp.put(localfile, remotefile)
            except Exception as e:
                self.scriptwriting_logger.error(u"" + str(e))
            else:
                self.scriptwriting_logger.info(u" Copy successful")
        else:
            self.scriptwriting_logger.info(u" Copying: " + localfile + " -> " + remotefile)
            try:
                remotedir = os.path.dirname(remotefile)
                shutil.copy(localfile, remotedir)
            except Exception as e:
                self.scriptwriting_logger.error(u"" + str(e))
            else:
                self.scriptwriting_logger.info(u" Copy successful")

    def rexists(self, path, stfp):
        if stfp:
            try:
                stfp.stat(path)
            except IOError as e:
                return False
            else:
                return True
        else:
            try:
                os.path.exists(path)
            except IOError as error:
                if error[0] == 2:
                    return False
            else:
                return True
    def check_perf_event_paranoid(self, job_settings):
        if job_settings["use_ssh"]:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                if len(job_settings["private_key"]) > 0:
                    key = paramiko.RSAKey.from_private_key_file(job_settings["private_key"])
                    client.connect(job_settings["server"], username=job_settings["username"], pkey=key)
                else:
                    client.connect(job_settings["server"], username=job_settings["username"],
                                   password=job_settings["password"])
                perf_event_paranoid_out = self.execute_command("cat /proc/sys/kernel/perf_event_paranoid", client=client,
                                                           return_output=True)
                client.close()
                perf_event_paranoid = perf_event_paranoid_out.read().decode("utf-8")
                match = re.match("[-0-9]+", perf_event_paranoid)
                if match:
                    return match.group(0)
                else:
                    return "None"
            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                client.close()
                return str(e)
        else:
            perf_event_paranoid_out = self.execute_command("cat /proc/sys/kernel/perf_event_paranoid",
                                                           return_output=True)
            return perf_event_paranoid_out.decode('utf8')


    def check_connection(self, job_settings):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if len(job_settings["private_key"]) > 0:
                key = paramiko.RSAKey.from_private_key_file(job_settings["private_key"])
                client.connect(job_settings["server"], username=job_settings["username"], pkey=key)
            else:
                client.connect(job_settings["server"], username=job_settings["username"], password=job_settings["password"])
            client.close()
            return ""
        except (BadHostKeyException, AuthenticationException,
                SSHException, socket.error) as e:
            client.close()
            return str(e)

    def get_failed_paths(self, job_settings):
        if self.use_ssh:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if len(job_settings["private_key"]) > 0:
                key = paramiko.RSAKey.from_private_key_file(job_settings["private_key"])
                client.connect(job_settings["server"], username=job_settings["username"], pkey=key)
            else:
                client.connect(job_settings["server"], username=job_settings["username"], password=job_settings["password"])
            stfp = client.open_sftp()
        else:
            client = None
            stfp = None
        failed_paths = []
        paths = self.bin_path.split(":")
        paths += self.lib_path.split(":")
        paths += self.preload.split(":")
        paths.append(self.exe)
        paths.append(self.working_dir)
        for path in paths:
            if len(path) > 0:
                if not self.rexists(path, stfp):
                    failed_paths.append(path)
        if self.use_ssh:
            stfp.close()
            client.close()
        return failed_paths

    def execute_commands(self, local_data, job_settings, perf_script, stack_collapse_script):
        if self.use_ssh:
            self.scriptwriting_logger.info(u" Open ssh connection")
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if len(job_settings["private_key"]) > 0:
                key = paramiko.RSAKey.from_private_key_file(job_settings["private_key"])
                client.connect(job_settings["server"], username=job_settings["username"], pkey=key)
            else:
                client.connect(job_settings["server"],username=job_settings["username"],password=job_settings["password"])
            self.scriptwriting_logger.info(u" Open stfp connection")
            stfp = client.open_sftp()
        else:
            client = None
            stfp = None
        root_directory = self.root_directory
        localfile = os.path.join(root_directory, "perl" + os.sep + stack_collapse_script)
        remotefile = job_settings["working_directory_linux"] + "/" + stack_collapse_script
        self.execute_command("rm -f {}".format(remotefile), client)
        self.put_file(localfile, remotefile, stfp)
        self.execute_command("chmod 500 {}".format(remotefile), client)
        for mpi_config_file in self.mpi_config_files:
            localfile = os.path.join(root_directory, local_data + os.sep + mpi_config_file)
            remotefile = job_settings["working_directory_linux"] + "/" + mpi_config_file
            self.execute_command("rm -f {}".format(remotefile), client)
            self.put_file(localfile, remotefile, stfp)
        localfile = os.path.join(root_directory, local_data + os.sep + perf_script)
        remotefile = job_settings["working_directory_linux"] + "/" + perf_script
        self.execute_command("rm -f {}".format(remotefile), client)
        self.put_file(localfile, remotefile, stfp)
        self.execute_command("chmod 500 {}".format(remotefile), client)
        self.execute_command(remotefile, client)
        self.execute_command("rm -f {}".format(remotefile), client)
        remotefile = job_settings["working_directory_linux"] + "/" + self.job_id + ".results"
        localfile = os.path.join(root_directory, local_data + os.sep + self.job_id + ".results")
        self.get_file(remotefile, localfile, stfp)
        results_file = os.path.join(root_directory, local_data + os.sep + self.job_id + ".results")
        with open(results_file, 'r') as results:
            for line in results:
                if not (re.match("event_counter", line) or
                        re.match("time_interval", line) or
                        re.match("cpu_id", line) or
                        re.match("system_wide", line)):
                    collapsed_file = line.strip()
                    remotefile = job_settings["working_directory_linux"] + "/" + collapsed_file
                    localfile = os.path.join(root_directory, local_data + os.sep + collapsed_file)
                    self.get_file(remotefile, localfile, stfp)
        if self.use_ssh:
            stfp.close()
            client.close()
            self.scriptwriting_logger.info(u" Close stfp connection")
            self.scriptwriting_logger.info(u" Close ssh connection")

        with open(results_file, 'r') as results:
            for line in results:
                if not (re.match("event_counter", line) or
                        re.match("time_interval", line) or
                        re.match("cpu_id", line) or
                        re.match("system_wide", line)):
                    l = line.strip()
                    orig_file = local_data + os.sep + l
                    if self.system_wide:
                        modify_system_wide_process_ids(orig_file)
                    else:
                        orig_pid = re.findall("proc([0-9]+)", l)
                        try:
                            modify_process_ids(orig_pid[0], orig_file)
                        except Exception as e:
                            raise Exception("Error reading results: \"" + line.strip() + "\"")

        if self.system_wide:
            replace_results_file(local_data, results_file, self.job_id)

        done_file = local_data + os.sep + self.job_id + ".done"
        f = io.open(done_file,'wb')
        f.close()

    def write_perf_script(self,local_data,stack_collapse_script):
        script_name = self.job_id + "_perf.sh"
        script_path = local_data + os.sep + script_name
        f = open(script_path,'wb')
        command = "#!/bin/sh\n\n"
        f.write(command.encode())
        command = "cd " + self.working_dir + "\n"
        f.write(command.encode())
        command = get_remove_old_data_command(self.job_id, self.system_wide)
        f.write(command.encode())
        if not self.use_lsf:
            if len(self.lib_path) > 0:
                command = "LD_LIBRARY_PATH={}:$LD_LIBRARY_PATH export LD_LIBRARY_PATH\n".format(self.lib_path)
                f.write(command.encode())
            if len(self.preload) > 0:
                command = "LD_PRELOAD={} export LD_PRELOAD\n".format(self.preload)
                f.write(command.encode())
            if len(self.bin_path) > 0:
                command = "PATH={}:$PATH export PATH\n".format(self.bin_path)
                f.write(command.encode())
            if len(self.env_variables) > 0:
                for env_var in self.env_variables.split(","):
                    var = env_var.split("=")[0]
                    command = env_var + " export " + var + "\n"
                    f.write(command.encode())

        num_nodes = ((self.processes - 1) // self.processes_per_node) + 1
        perf_event_groups = self.cpu_definition.get_perf_event_groups(self.run_duration, self.max_events_per_run, self.fixed_counter, self.count)
        n_group = 0
        sudo = self.sudo_command
        for group in perf_event_groups:
            if group["event_type"] == "Trace":
                events = [re.sub("trace-", "", event) for event in group["events"]]
            else:
                events = group["events"]
            flag = group["flag"]
            counter = group["event_counter"]
            n_group += 1
            exe_args = self.exe_args
            replacement_string = "_" + self.job_id + "_" + str(n_group)
            for m in re.findall("([\S\$]+)",self.copy_files):
                orig_file = re.sub("\$","",m)
                new_file = re.sub("\$",replacement_string,m)
                command = "cp " + orig_file + " " + new_file + "\n"
                f.write(command.encode())
            exe_args = re.sub("\$",replacement_string,exe_args)
            if self.use_mpirun:
                config_name = self.job_id + "run" + str(n_group) + "_mpiconfig"
                config_path = local_data + os.sep + config_name
                self.mpi_config_files.append(config_name)
                mpi_config_file = open(config_path,'wb')
                if self.system_wide:
                    for nid in range(0, num_nodes):
                        mpirun_command = "-np 1 " + self.local_mpirun_params
                        event_list = ",".join(events)
                        perf_out_file = get_perf_out_file_name(self.job_id, nid, n_group, self.system_wide)
                        perf_command = sudo + self.perf_params
                        perf_command += " -e " + event_list + " " + " ".join([flag, str(counter)])
                        perf_command += " -o " + perf_out_file
                        exe_command = self.exe + " " + exe_args
                        command = " ".join([mpirun_command, perf_command, exe_command]) + "\n"
                        mpi_config_file.write(command.encode())
                        if self.processes_per_node > 1:
                            np = self.processes_per_node - 1
                            mpirun_command = "-np " + str(np)
                            exe_command = self.exe + " " + exe_args
                            command = " ".join([mpirun_command, exe_command]) + "\n"
                            mpi_config_file.write(command.encode())
                else:
                    for pid in range(0, self.processes):
                        if pid % self.proc_attach == 0:
                            mpirun_command = "-np 1 " + self.local_mpirun_params
                            event_list = ",".join(events)
                            perf_out_file = get_perf_out_file_name(self.job_id, pid, n_group, self.system_wide)
                            perf_command = sudo + self.perf_params
                            perf_command += " -e " + event_list + " " + " ".join([flag, str(counter)])
                            perf_command += " -o " + perf_out_file
                            exe_command = self.exe + " " + exe_args
                            command = " ".join([mpirun_command, perf_command, exe_command]) + "\n"
                            mpi_config_file.write(command.encode())
                        elif pid % self.proc_attach == 1:
                            if pid + self.proc_attach - 1 > self.processes:
                                np = self.processes - pid
                            else:
                                np = self.proc_attach - 1
                            mpirun_command = "-np " + str(np)
                            exe_command = self.exe + " " + exe_args
                            command = " ".join([mpirun_command, exe_command]) + "\n"
                            mpi_config_file.write(command.encode())
                mpi_config_file.close()
                if self.use_lsf:
                    lsf_command = "bsub " + self.lsf_params
                    out_file = self.job_id + "run" + str(n_group) + ".out"
                    err_file = self.job_id + "run" + str(n_group) + ".err"
                    lsf_command += " -e " + err_file + " -o " + out_file
                    command = lsf_command + " mpirun " + self.global_mpirun_params + " " + self.mpirun_appfile + " " + config_name
                else:
                    command = "mpirun " + self.global_mpirun_params + " " + self.mpirun_appfile + " " + config_name
            else:
                event_list = ",".join(events)
                perf_out_file = get_perf_out_file_name(self.job_id, 0, n_group, self.system_wide)
                perf_command = sudo + self.perf_params
                perf_command += " -e " + event_list + " " + " ".join([flag, str(counter)])
                perf_command += " -o " + perf_out_file
                exe_command = self.exe + " " + exe_args
                if self.use_lsf:
                    lsf_command = "bsub " + self.lsf_params
                    out_file = self.job_id + "run" + str(n_group) + ".out"
                    err_file = self.job_id + "run" + str(n_group) + ".err"
                    lsf_command += " -e " + err_file + " -o " + out_file
                    command = " ".join([lsf_command, perf_command, exe_command])
                else:
                    command = " ".join([perf_command, exe_command])
            if self.run_parallel:
                command += " &\n"
                f.write(command.encode())
            else:
                command += "\n"
                f.write(command.encode())
                command = "wait\n"
                f.write(command.encode())
        command = "wait\n"
        f.write(command.encode())

        for n_group in range(1,len(perf_event_groups)+1):
            for pid in range(0,self.processes):
                if self.system_wide and pid == num_nodes:
                    break
                command = get_perf_script_command(self.job_id, pid, n_group, self.system_wide, self.use_lsf, self.lsf_env, self.queue, self.sudo_command)
                f.write(command.encode())
        command = "wait\n"
        f.write(command.encode())

        n_group = 0
        for group in perf_event_groups:
            n_group += 1
            trace_event = None
            if group["event_type"] == "Trace":
                trace_event = re.sub("trace-", "", group["events"][0])
            for pid in range(0,self.processes):
                if self.system_wide and pid == num_nodes:
                    break
                command = get_stack_collapse_command(self.job_id, pid, n_group, self.dt, stack_collapse_script, self.system_wide, trace_event)
                f.write(command.encode())
        command = "wait\n"
        f.write(command.encode())

        results_file = self.job_id + ".results"
        n_group = 0
        n = 0
        for group in perf_event_groups:
            n_group += 1
            for event in group["events"]:
                n += 1
                if self.fixed_counter:
                    counter = str(self.count)
                else:
                    counter = str(group["event_counter"])
                if n == 1:
                    op = " > "
                else:
                    op = " >> "
                command = "echo " + "'event_counter-" + event + ":" + "run-" + str(n_group) + ":" + counter + "'" + op + results_file + "\n"
                f.write(command.encode())
                if group["event_type"] == "Trace":
                    break
        command = "echo " + "'time_interval:" + str(self.dt) + "'" + " >> " + results_file + "\n"
        f.write(command.encode())
        command = "echo " + "'cpu_id:" + self.cpu + "'" + " >> " + results_file + "\n"
        f.write(command.encode())
        if self.system_wide:
            command = "echo " + "'system_wide'" + " >> " + results_file + "\n"
            f.write(command.encode())
        command = get_copy_results_command(self.job_id, results_file, self.system_wide)
        f.write(command.encode())

        f.close()

        return script_name


