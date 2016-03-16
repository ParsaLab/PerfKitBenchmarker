# Copyright 2015 PerfKitBenchmarker Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Runs Cloudsuite3.0 Data Caching benchmark
   More info: http://cloudsuite.ch/datacaching
"""

import re

from perfkitbenchmarker import configs
# from perfkitbenchmarker import flags
from perfkitbenchmarker import sample

# TODO define properiate flags
# flags.DEFINE_string('ima_dataset',
#                     '/data/ml-latest-small',
#                     'Dataset to use for training.')
# flags.DEFINE_string('ima_ratings_file',
#                     '/data/myratings.csv',
#                     'Ratings file to give the recommendation for.')
# FLAGS = flags.FLAGS

BENCHMARK_NAME = 'cloudsuite_data_caching'
BENCHMARK_CONFIG = """
cloudsuite_data_caching:
  description: >
    Runs Cloudsuite3.0 Data Caching benchmark.
  vm_groups:
    server:
      vm_spec:
        GCP:
            machine_type: n1-standard-8
            image: null
            zone: us-central1-a
      disk_spec:
        GCP:
            disk_type: pd-standard
            disk_size: 500
            mount_point: /scratch
    client:
      vm_spec:
        GCP:
            machine_type: n1-standard-8
            image: null
            zone: us-central1-a
      disk_spec:
        GCP:
            disk_type: pd-standard
            disk_size: 500
            mount_point: /scratch
"""


def GetConfig(user_config):
  config = configs.LoadConfig(BENCHMARK_CONFIG, user_config, BENCHMARK_NAME)
# if FLAGS['server_count'].present:
#   config['vm_groups']['server']['server_count'] = FLAGS.server_count
  return config


def _HasDocker(vm):
  resp, _ = vm.RemoteCommand('command -v docker',
                             ignore_failure=True,
                             suppress_warning=True)
  if resp.rstrip() == "":
    return False
  else:
    return True


def Prepare(benchmark_spec):
  """Install docker. Pull the required images from DockerHub. Create datasets.
  Start Spark master and workers.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.
  """
  vms = benchmark_spec.vms
  server_vm = benchmark_spec.vm_groups['server'][0]
  client_vm = benchmark_spec.vm_groups['client'][0]

# Make sure docker is installed on all VMs.
  for vm in vms:
    if not _HasDocker(vm):
      vm.Install('docker')

    # Prepare and start the server VM.
  server_vm.RemoteCommand('sudo docker pull cloudsuite/data-caching:server')
  server_vm.RemoteCommand("echo '%s    dc-client' | sudo tee -a /etc/hosts >"
                          " /dev/null" % client_vm.internal_ip)
  server_vm.RemoteCommand('sudo docker run --name dc-server --net host -d'
                          'cloudsuite/data-caching:server')

# Prepare the client.
  client_vm.RemoteCommand('sudo docker pull cloudsuite/data-caching:client')
  client_vm.RemoteCommand("echo '%s    dc-server' | sudo tee -a /etc/hosts >"
                          " /dev/null" % server_vm.internal_ip)


def _ParseOutput(output_str):
    numbers = re.findall(r"([-+]?\d*\.\d+|\d+)",
                         " ".join(output_str.splitlines(1)[-4:]))
    results = []
    results.append(sample.Sample("Requests per second",
                                 float(numbers[1]), "req/s"))
    results.append(sample.Sample("Average latency",
                                 float(numbers[7]), "ms"))
    results.append(sample.Sample("90th percentile latency",
                                 float(numbers[8]), "ms"))
    results.append(sample.Sample("95th percentile latency",
                                 float(numbers[9]), "ms"))
    results.append(sample.Sample("99th percentile latency",
                                 float(numbers[10]), "ms"))

    avg_req_rem = 0
    for num in numbers[-9:-1]:
        avg_req_rem += int(num)
    avg_req_rem /= 8.0

    results.append(sample.Sample("Average outstanding requests per requester",
                                 float(avg_req_rem), "reqs"))

    return results


def Run(benchmark_spec):
  """Run the in-memory analytics benchmark.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.

  Returns:
    A list of sample.Sample objects.
  """

  client_vm = benchmark_spec.vm_groups['client'][0]

  benchmark_cmd = ('sudo docker run --rm --name dc-client --net host'
                   ' cloudsuite/data-caching:client')

  stdout, _ = client_vm.RemoteCommand(benchmark_cmd, should_log=True)

  return _ParseOutput(stdout)


def Cleanup(benchmark_spec):
  """Stop and remove docker containers. Remove images.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.
  """

  server_vm = benchmark_spec.vm_groups['server'][0]
  client_vm = benchmark_spec.vm_groups['client'][0]

  server_vm.RemoteCommand('sudo docker stop dc-server')
  server_vm.RemoteCommand('sudo docker rm dc-server')
  server_vm.RemoteCommand('sudo docker rmi cloudsuite/data-caching:server')
  client_vm.RemoteCommand('sudo docker stop dc-client')
  client_vm.RemoteCommand('sudo docker rm dc-client')
  client_vm.RemoteCommand('sudo docker rmi cloudsuite/data-caching:client')
