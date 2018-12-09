import io
import os
import re
import shutil
import threading
import subprocess
import pathlib
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

def get_sudo_command(run_as_root, env_variables, library_path, ld_preload):
    if not run_as_root:
        return ""
    else:
        vars = []
        for var in env_variables.split(","):
            var_name = var.partition("=")[0]
            vars.append(var_name + "=$" + var_name)
        if len(ld_preload) > 0:
            vars.append("LD_PRELOAD=" + ld_preload)
        if len(library_path) > 0:
            vars.append("LD_LIBRARY_PATH=" + library_path)
        var_string = " ".join(vars)
        return "sudo " + var_string + " "

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
        command = "perf record -g -a"
    else:
        command = "perf record -g"
    return command


def get_perf_out_file_name(job_id, pid, n_group, system_wide):
    if system_wide:
        perf_out_file = job_id + "_host" + str(pid) + "run" + str(n_group) + ".perf"
    else:
        perf_out_file = job_id + "_proc" + str(pid) + "run" + str(n_group) + ".perf"
    return perf_out_file


def get_perf_script_command(in_file, out_file, system_wide, use_lsf, env, queue, sudo=""):
    if system_wide:
        flags = "comm,cpu,pid,tid,time,event,ip,sym,dso"
    else:
        flags = "comm,pid,tid,time,event,ip,sym,dso"
    if use_lsf:
        command = 'bsub -K -env {} -e bjobs.err -o bjobs.out -q {} -n 1 \"{}perf script -F {} --show-kernel-path -i {} > {} \" &\n'.format(
        env, queue, sudo, flags, in_file, out_file)
    else:
        command = "{}perf script -F {} --show-kernel-path -i {} > {} &\n".format(sudo, flags, in_file, out_file)
    return command


def get_stack_collapse_command(in_file, out_file, dt, stack_collapse_script, system_wide, trace_event=None):
    if system_wide:
        command = 'cat {} | perl {} --pid --tid --output_file={} --dt={} --accumulate'.format(in_file, stack_collapse_script, out_file, dt)
    else:
        command = 'cat {} | perl {} --pid --tid --output_file={} --dt={}'.format(in_file, stack_collapse_script, out_file, dt)
    if trace_event:
        command += " --trace_event=" + trace_event
    command += " &\n"
    return command


class Job:

    def __init__(self, job_id, copy_files, run_parallel, run_system_wide, run_as_root, processes,
                 processes_per_node, exe, exe_args, working_dir, run_duration,
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
        self.sudo_command = get_sudo_command(run_as_root, env_variables, self.lib_path, self.preload)
        self.global_mpirun_params = global_mpirun_params
        self.local_mpirun_params = local_mpirun_params
        self.mpirun_appfile = get_mpirun_appfile(mpirun_version)
        self.lsf_params = get_lsf_params(lsf_params, lib_path, preload, env_variables, bin_path)
        self.perf_params = perf_params
        self.use_mpirun = use_mpirun
        self.use_lsf = use_lsf
        self.use_ssh = use_ssh
        self.max_events_per_run = max_events_per_run


class JobHandler:

    def __init__(self, root_directory, job=None):
        self.root_directory = root_directory
        self.job = job
        self.stack_collapse_script = 'stackcollapse-perf-modified.pl'
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
        perf_script = self.write_perf_script(local_data)
        self.scriptwriting_logger.info(u" Setup background threads")
        working_dir = job_settings["working_directory_linux"]
        try:
            background_thread = threading.Thread(target=self.run_perf_job,
                                                 args=(working_dir, self.job.use_ssh, self.job.job_id, local_data,
                                                       perf_script, self.job.system_wide, self.job.mpi_config_files,
                                                       job_settings))
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
                hostname = job_settings["server"]
                port = 22
                match = re.match("(.+):([0-9]+)", hostname)
                if match:
                    hostname = match.group(1)
                    port = int(match.group(2))
                if len(job_settings["private_key"]) > 0:
                    key = paramiko.RSAKey.from_private_key_file(job_settings["private_key"])
                    client.connect(hostname, port=port, username=job_settings["username"], pkey=key)
                else:
                    client.connect(hostname, port=port, username=job_settings["username"],
                                   password=job_settings["password"])
                perf_event_paranoid_out = self.execute_command("cat /proc/sys/kernel/perf_event_paranoid",
                                                               client=client, return_output=True)
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
            hostname = job_settings["server"]
            port = 22
            match = re.match("(.+):([0-9]+)", hostname)
            if match:
                hostname = match.group(1)
                port = int(match.group(2))
            if len(job_settings["private_key"]) > 0:
                key = paramiko.RSAKey.from_private_key_file(job_settings["private_key"])
                client.connect(hostname, port=port, username=job_settings["username"], pkey=key)
            else:
                client.connect(hostname, port=port, username=job_settings["username"],
                               password=job_settings["password"])
            client.close()
            return ""
        except (BadHostKeyException, AuthenticationException,
                SSHException, socket.error) as e:
            client.close()
            return str(e)


    def get_failed_paths(self, job , job_settings):
        if job.use_ssh:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            hostname = job_settings["server"]
            port = 22
            match = re.match("(.+):([0-9]+)", hostname)
            if match:
                hostname = match.group(1)
                port = int(match.group(2))
            if len(job_settings["private_key"]) > 0:
                key = paramiko.RSAKey.from_private_key_file(job_settings["private_key"])
                client.connect(hostname, port=port, username=job_settings["username"], pkey=key)
            else:
                client.connect(hostname, port=port, username=job_settings["username"], password=job_settings["password"])
            stfp = client.open_sftp()
        else:
            client = None
            stfp = None
        failed_paths = []
        paths = job.bin_path.split(":")
        paths += job.lib_path.split(":")
        paths += job.preload.split(":")
        paths.append(job.exe)
        paths.append(job.working_dir)
        for path in paths:
            if len(path) > 0:
                if not self.rexists(path, stfp):
                    failed_paths.append(path)
        if job.use_ssh:
            stfp.close()
            client.close()
        return failed_paths

    def run_perf_job(self, working_directory, use_ssh, job_id, local_data, perf_script,
                     system_wide, mpi_config_files, job_settings=None):
        if use_ssh:
            self.scriptwriting_logger.info(u" Open ssh connection")
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            hostname = job_settings["server"]
            port = 22
            match = re.match("(.+):([0-9]+)", hostname)
            if match:
                hostname = match.group(1)
                port = int(match.group(2))
            if len(job_settings["private_key"]) > 0:
                key = paramiko.RSAKey.from_private_key_file(job_settings["private_key"])
                client.connect(hostname, port=port, username=job_settings["username"], pkey=key)
            else:
                client.connect(hostname, port=port, username=job_settings["username"],password=job_settings["password"])
            self.scriptwriting_logger.info(u" Open stfp connection")
            stfp = client.open_sftp()
        else:
            client = None
            stfp = None
        root_directory = self.root_directory
        localfile = os.path.join(root_directory, "perl" + os.sep + self.stack_collapse_script)
        remotefile = working_directory + "/" + self.stack_collapse_script
        self.execute_command("rm -f {}".format(remotefile), client)
        self.put_file(localfile, remotefile, stfp)
        self.execute_command("chmod 500 {}".format(remotefile), client)
        for mpi_config_file in mpi_config_files:
            localfile = os.path.join(root_directory, local_data + os.sep + mpi_config_file)
            remotefile = working_directory + "/" + mpi_config_file
            self.execute_command("rm -f {}".format(remotefile), client)
            self.put_file(localfile, remotefile, stfp)
        localfile = os.path.join(root_directory, local_data + os.sep + perf_script)
        remotefile = working_directory + "/" + perf_script
        self.execute_command("rm -f {}".format(remotefile), client)
        self.put_file(localfile, remotefile, stfp)
        self.execute_command("chmod 500 {}".format(remotefile), client)
        self.execute_command(remotefile, client)
        self.execute_command("rm -f {}".format(remotefile), client)
        remotefile = working_directory + "/" + job_id + ".results"
        localfile = os.path.join(root_directory, local_data + os.sep + job_id + ".results")
        self.get_file(remotefile, localfile, stfp)
        results_file = os.path.join(root_directory, local_data + os.sep + job_id + ".results")
        with open(results_file, 'r') as results:
            for line in results:
                if not (re.match("event_counter", line) or
                        re.match("time_interval", line) or
                        re.match("cpu_id", line) or
                        re.match("system_wide", line)):
                    collapsed_file = line.strip()
                    remotefile = working_directory + "/" + collapsed_file
                    localfile = os.path.join(root_directory, local_data + os.sep + collapsed_file)
                    self.get_file(remotefile, localfile, stfp)
        if use_ssh:
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
                    if system_wide:
                        modify_system_wide_process_ids(orig_file)
                    else:
                        orig_pid = re.findall("proc([0-9]+)", l)
                        try:
                            modify_process_ids(orig_pid[0], orig_file)
                        except Exception as e:
                            raise Exception("Error reading results: \"" + line.strip() + "\"")

        if system_wide:
            replace_results_file(local_data, results_file, job_id)

        done_file = local_data + os.sep + job_id + ".done"
        f = io.open(done_file, 'wb')
        f.close()

    def write_perf_script(self,local_data):
        job = self.job
        script_name = job.job_id + "_perf.sh"
        script_path = local_data + os.sep + script_name
        f = open(script_path,'wb')
        command = "#!/bin/sh\n\n"
        f.write(command.encode())
        command = "cd " + job.working_dir + "\n"
        f.write(command.encode())
        # clear old data
        if job.system_wide:
            event_files = job.job_id + "_host*"
        else:
            event_files = job.job_id + "_proc*"
        command = "rm -f " + event_files + "\n"
        f.write(command.encode())
        if not job.use_lsf:
            if len(job.lib_path) > 0:
                command = "LD_LIBRARY_PATH={}:$LD_LIBRARY_PATH export LD_LIBRARY_PATH\n".format(job.lib_path)
                f.write(command.encode())
            if len(job.preload) > 0:
                command = "LD_PRELOAD={} export LD_PRELOAD\n".format(job.preload)
                f.write(command.encode())
            if len(job.bin_path) > 0:
                command = "PATH={}:$PATH export PATH\n".format(job.bin_path)
                f.write(command.encode())
            if len(job.env_variables) > 0:
                for env_var in job.env_variables.split(","):
                    var = env_var.split("=")[0]
                    command = env_var + " export " + var + "\n"
                    f.write(command.encode())

        num_nodes = ((job.processes - 1) // job.processes_per_node) + 1
        perf_event_groups = job.cpu_definition.get_perf_event_groups(job.run_duration, job.max_events_per_run,
                                                                     job.fixed_counter, job.count)
        n_group = 0
        sudo = job.sudo_command
        for group in perf_event_groups:
            if group["event_type"] == "Trace":
                events = [re.sub("trace-", "", event) for event in group["events"]]
            else:
                events = group["events"]
            flag = group["flag"]
            counter = group["event_counter"]
            n_group += 1
            exe_args = job.exe_args
            replacement_string = "_" + job.job_id + "_" + str(n_group)
            for m in re.findall("([\S\$]+)",job.copy_files):
                orig_file = re.sub("\$","",m)
                new_file = re.sub("\$",replacement_string,m)
                command = "cp " + orig_file + " " + new_file + "\n"
                f.write(command.encode())
            exe_args = re.sub("\$",replacement_string,exe_args)
            if job.use_mpirun:
                config_name = job.job_id + "run" + str(n_group) + "_mpiconfig"
                config_path = local_data + os.sep + config_name
                job.mpi_config_files.append(config_name)
                mpi_config_file = open(config_path,'wb')
                if job.system_wide:
                    for nid in range(0, num_nodes):
                        mpirun_command = "-np 1 " + job.local_mpirun_params
                        event_list = ",".join(events)
                        perf_out_file = get_perf_out_file_name(job.job_id, nid, n_group, job.system_wide)
                        perf_command = sudo + job.perf_params
                        perf_command += " -e " + event_list + " " + " ".join([flag, str(counter)])
                        perf_command += " -o " + perf_out_file
                        exe_command = job.exe + " " + exe_args
                        command = " ".join([mpirun_command, perf_command, exe_command]) + "\n"
                        mpi_config_file.write(command.encode())
                        if job.processes_per_node > 1:
                            np = job.processes_per_node - 1
                            mpirun_command = "-np " + str(np)
                            exe_command = job.exe + " " + exe_args
                            command = " ".join([mpirun_command, exe_command]) + "\n"
                            mpi_config_file.write(command.encode())
                else:
                    for pid in range(0, job.processes):
                        if pid % job.proc_attach == 0:
                            mpirun_command = "-np 1 " + job.local_mpirun_params
                            event_list = ",".join(events)
                            perf_out_file = get_perf_out_file_name(job.job_id, pid, n_group, job.system_wide)
                            perf_command = sudo + job.perf_params
                            perf_command += " -e " + event_list + " " + " ".join([flag, str(counter)])
                            perf_command += " -o " + perf_out_file
                            exe_command = job.exe + " " + exe_args
                            command = " ".join([mpirun_command, perf_command, exe_command]) + "\n"
                            mpi_config_file.write(command.encode())
                        elif pid % job.proc_attach == 1:
                            if pid + job.proc_attach - 1 > job.processes:
                                np = job.processes - pid
                            else:
                                np = job.proc_attach - 1
                            mpirun_command = "-np " + str(np)
                            exe_command = job.exe + " " + exe_args
                            command = " ".join([mpirun_command, exe_command]) + "\n"
                            mpi_config_file.write(command.encode())
                mpi_config_file.close()
                if job.use_lsf:
                    lsf_command = "bsub " + job.lsf_params
                    out_file = job.job_id + "run" + str(n_group) + ".out"
                    err_file = job.job_id + "run" + str(n_group) + ".err"
                    lsf_command += " -e " + err_file + " -o " + out_file
                    command = lsf_command + " mpirun " + job.global_mpirun_params \
                              + " " + job.mpirun_appfile + " " + config_name
                else:
                    command = "mpirun " + job.global_mpirun_params + " " + job.mpirun_appfile + " " + config_name
            else:
                event_list = ",".join(events)
                perf_out_file = get_perf_out_file_name(job.job_id, 0, n_group, job.system_wide)
                perf_command = sudo + job.perf_params
                perf_command += " -e " + event_list + " " + " ".join([flag, str(counter)])
                perf_command += " -o " + perf_out_file
                exe_command = job.exe + " " + exe_args
                if job.use_lsf:
                    lsf_command = "bsub " + job.lsf_params
                    out_file = job.job_id + "run" + str(n_group) + ".out"
                    err_file = job.job_id + "run" + str(n_group) + ".err"
                    lsf_command += " -e " + err_file + " -o " + out_file
                    command = " ".join([lsf_command, perf_command, exe_command])
                else:
                    command = " ".join([perf_command, exe_command])
            if job.run_parallel:
                command += " &\n"
                f.write(command.encode())
            else:
                command += "\n"
                f.write(command.encode())
                command = "wait\n"
                f.write(command.encode())
        command = "wait\n"
        f.write(command.encode())

        for n_group in range(1, len(perf_event_groups)+1):
            for pid in range(0, job.processes):
                if job.system_wide and pid == num_nodes:
                    break
                if job.system_wide:
                    in_file = job.job_id + "_host" + str(pid) + "run" + str(n_group) + ".perf"
                    out_file = job.job_id + "_host" + str(pid) + "run" + str(n_group) + ".stacks"
                else:
                    in_file = job.job_id + "_proc" + str(pid) + "run" + str(n_group) + ".perf"
                    out_file = job.job_id + "_proc" + str(pid) + "run" + str(n_group) + ".stacks"
                command = get_perf_script_command(in_file, out_file, job.system_wide,
                                                  job.use_lsf, job.lsf_env, job.queue, job.sudo_command)
                f.write(command.encode())
        command = "wait\n"
        f.write(command.encode())

        n_group = 0
        for group in perf_event_groups:
            n_group += 1
            trace_event = None
            if group["event_type"] == "Trace":
                trace_event = re.sub("trace-", "", group["events"][0])
            for pid in range(0, job.processes):
                if job.system_wide and pid == num_nodes:
                    break
                if job.system_wide:
                    in_file = job.job_id + "_host" + str(pid) + "run" + str(n_group) + ".stacks"
                    out_file = job.job_id + "_host" + str(pid)
                else:
                    in_file = job.job_id + "_proc" + str(pid) + "run" + str(n_group) + ".stacks"
                    out_file = job.job_id + "_proc" + str(pid)
                command = get_stack_collapse_command(in_file, out_file, job.dt, self.stack_collapse_script,
                                                     job.system_wide, trace_event)
                f.write(command.encode())
        command = "wait\n"
        f.write(command.encode())

        results_file = job.job_id + ".results"
        n_group = 0
        n = 0
        for group in perf_event_groups:
            n_group += 1
            for event in group["events"]:
                n += 1
                if job.fixed_counter:
                    counter = str(job.count)
                else:
                    counter = str(group["event_counter"])
                if n == 1:
                    op = " > "
                else:
                    op = " >> "
                command = "echo " + "'event_counter-" + event + ":" + "run-" + str(n_group)\
                          + ":" + counter + "'" + op + results_file + "\n"
                f.write(command.encode())
                if group["event_type"] == "Trace":
                    break
        command = "echo " + "'time_interval:" + str(job.dt) + "'" + " >> " + results_file + "\n"
        f.write(command.encode())
        command = "echo " + "'cpu_id:" + job.cpu + "'" + " >> " + results_file + "\n"
        f.write(command.encode())
        if job.system_wide:
            command = "echo " + "'system_wide'" + " >> " + results_file + "\n"
            f.write(command.encode())
        if job.system_wide:
            command = "for file in " + job.job_id + "_host*_*; do echo $file >> " + results_file + "; done\n"
        else:
            command = "for file in " + job.job_id + "_proc*_*; do echo $file >> " + results_file + "; done\n"
        f.write(command.encode())

        f.close()

        return script_name

    def convert_perf_data(self, perf_data_files, local_data, working_dir):
        command = "cd {}; perf script --header-only -i {} | grep \"cmdline\"".format(working_dir, perf_data_files[0])
        output = subprocess.check_output(command, shell=True)
        command_line = output.decode("utf-8")
        if re.match(" -a ", command_line):
            system_wide = True
        else:
            system_wide = False
        run = 0
        for file in perf_data_files:
            run += 1
            command = "cd {}; perf evlist -F -i {}".format(working_dir, file)
            output = subprocess.check_output(command, shell=True)
            events = output.decode("utf-8")
            event_counters = {}
            event_runs = {}
            for event_info in events.split("\n"):
                match = re.match("(.*):.*(sample_period|sample_freq)=(\d+)", event_info)
                if match:
                    event = match.group(1)
                    period = match.group(3)
                    event_counters[event] = period
                    event_runs[event] = run
        job_id = pathlib.Path(perf_data_files[0]).stem
        script_name = job_id + "_perf.sh"
        script_path = local_data + os.sep + script_name
        f = open(script_path, 'wb')
        command = "#!/bin/sh\n\n"
        f.write(command.encode())
        command = "cd " + working_dir + "\n"
        f.write(command.encode())
        # clear old data
        if system_wide:
            event_files = job_id + "_host*"
        else:
            event_files = job_id + "_proc*"
        command = "rm -f " + event_files + "\n"
        f.write(command.encode())
        for n in range(len(perf_data_files)):
            in_file = perf_data_files[n]
            if system_wide:
                out_file = job_id + "_host" + str(0) + "run" + str(n+1) + ".stacks"
            else:
                out_file = job_id + "_proc" + str(0) + "run" + str(n+1) + ".stacks"
            command = get_perf_script_command(in_file, out_file, system_wide, False, "", "")
            f.write(command.encode())
        command = "wait\n"
        f.write(command.encode())

        trace_event = None
        if "cycles" in event_runs:
            trace_event = "cycles"
        elif "cpu-clock" in event_runs:
            trace_event = "cpu-clock"
        elif "task-clock" in event_runs:
            trace_event = "task-clock"

        dt = 10.0
        cpu = "General"
        for n in range(len(perf_data_files)):
            if system_wide:
                in_file = job_id + "_host" + str(0) + "run" + str(n+1) + ".stacks"
                out_file = job_id + "_host" + str(0)
            else:
                in_file = job_id + "_proc" + str(0) + "run" + str(n+1) + ".stacks"
                out_file = job_id + "_proc" + str(0)
            command = get_stack_collapse_command(in_file, out_file, dt, self.stack_collapse_script,
                                                 system_wide)
            f.write(command.encode())
        if trace_event:
            event_counters["trace-" + trace_event] = event_counters[trace_event]
            event_runs["trace-" + trace_event] = len(event_runs) + 1
            n = event_runs[trace_event]
            if system_wide:
                in_file = job_id + "_host" + str(0) + "run" + str(n) + ".stacks"
                out_file = job_id + "_host" + str(0)
            else:
                in_file = job_id + "_proc" + str(0) + "run" + str(n) + ".stacks"
                out_file = job_id + "_proc" + str(0)
            command = get_stack_collapse_command(in_file, out_file, dt, self.stack_collapse_script,
                                                 system_wide, trace_event)
            f.write(command.encode())
        command = "wait\n"
        f.write(command.encode())

        results_file = job_id + ".results"
        n = 0
        for event in event_counters:
            run = event_runs[event]
            n += 1
            counter = event_counters[event]
            if n == 1:
                op = " > "
            else:
                op = " >> "
            command = "echo " + "'event_counter-" + event + ":" + "run-" + str(
                run) + ":" + counter + "'" + op + results_file + "\n"
            f.write(command.encode())
        command = "echo " + "'time_interval:" + str(dt) + "'" + " >> " + results_file + "\n"
        f.write(command.encode())
        command = "echo " + "'cpu_id:" + cpu + "'" + " >> " + results_file + "\n"
        f.write(command.encode())
        if system_wide:
            command = "echo " + "'system_wide'" + " >> " + results_file + "\n"
            f.write(command.encode())
        if system_wide:
            command = "for file in " + job_id + "_host*_*; do echo $file >> " + results_file + "; done\n"
        else:
            command = "for file in " + job_id + "_proc*_*; do echo $file >> " + results_file + "; done\n"
        f.write(command.encode())

        f.close()

        self.run_perf_job(working_dir, False, job_id, local_data, script_name,
                              system_wide, [])

        return results_file




