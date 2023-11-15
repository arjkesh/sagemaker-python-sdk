"""Utilites for identifying and analyzing local gpu hardware"""
from __future__ import absolute_import

import subprocess
import multiprocessing
import logging
import shutil
from math import ceil, floor
from platform import system
from pathlib import Path
import psutil

logger = logging.getLogger(__name__)

# key = vCPUs
# for A100, vCPUs are the same. Distinguish by GPU memory
hardware_lookup = {
    "NVIDIA H100": {192: "ml.p5.48xlarge"},
    "NVIDIA A100": {
        96: {
            40: "ml.p4d.24xlarge",
            80: "ml.p4de.24xlarge",
        }
    },
    "NVIDIA V100": {
        8: "ml.p3.2xlarge",
        32: "ml.p3.8xlarge",
        64: "ml.p3.16xlarge",
        96: "ml.p3dn.24xlarge",
    },
    "NVIDIA K80": {
        4: "ml.p2.xlarge",
        32: "ml.p2.8xlarge",
        64: "ml.p2.16xlarge",
    },
    "NVIDIA T4": {
        4: "ml.g4dn.xlarge",
        8: "ml.g4dn.2xlarge",
        16: "ml.g4dn.4xlarge",
        32: "ml.g4dn.8xlarge",
        48: "ml.g4dn.12xlarge",
        64: "ml.g4dn.16xlarge",
    },
    "NVIDIA A10G": {
        4: "ml.g5n.xlarge",
        8: "ml.g5.2xlarge",
        16: "ml.g5.4xlarge",
        32: "ml.g5.8xlarge",
        48: "ml.g5.12xlarge",
        64: "ml.g5.16xlarge",
        96: "ml.g5.24xlarge",
        192: "ml.g5.48xlarge",
    },
}


def _get_available_gpus(log=True):
    """Detect the GPUs available on the device and their available resources"""
    try:
        gpu_query = ["nvidia-smi", "--query-gpu=name,memory.free", "--format=csv"]
        gpu_info_csv = subprocess.run(gpu_query, stdout=subprocess.PIPE, check=True)
        gpu_info = gpu_info_csv.stdout.decode("utf-8").splitlines()[1:]

        if log:
            logger.info("CUDA enabled hardware on the device: %s", gpu_info)

        return gpu_info
    except Exception as e:
        # for nvidia-smi to run, a cuda driver must be present
        raise ValueError("CUDA is not enabled on your device. %s" % str(e))


def _get_nb_instance():
    """Placeholder docstring"""
    gpu_info = _get_available_gpus(False)
    gpu_name, gpu_mem = gpu_info[0].split(", ")
    cpu_count = multiprocessing.cpu_count()

    hardware = hardware_lookup.get(gpu_name)
    if not hardware:
        logger.info("Could not detect the instance type for GPU: %s, %s", gpu_name, gpu_mem)
        return None

    if gpu_name == "NVIDIA A100":
        gpu_mem_mib = int(gpu_mem.split(" ")[0])
        gpu_mem_gb = gpu_mem_mib * 1024**2 / 1000**3

        if ceil(gpu_mem_gb) in hardware:
            instance_type = hardware.get(int(ceil(gpu_mem_gb)))
        else:
            instance_type = hardware.get(int(floor(gpu_mem_gb)))
    else:
        instance_type = hardware.get(cpu_count)

    logger.info(
        "Local instance_type %s detected. "
        "%s will be default when deploying to a SageMaker Endpoint. "
        "This default can be overriden in model.deploy()",
        instance_type,
        instance_type,
    )
    return instance_type


def _get_ram_usage_mb():
    """Placeholder docstring"""
    return psutil.virtual_memory()[3] / 1000000


def _check_disk_space(model_path: str):
    """Placeholder docstring"""
    usage = shutil.disk_usage(model_path)
    percentage_used = usage[1] / usage[0]
    if percentage_used >= 0.5:
        logger.warning(
            "%s percent of disk space used. Please consider freeing up disk space "
            "or increasing the EBS volume if you are on a SageMaker Notebook.",
            percentage_used * 100,
        )


def _check_docker_disk_usage():
    """Fetch the local docker container disk usage.

    Args:
        None
    Returns:
        None
    """
    try:
        docker_path = "/var/lib/docker"
        # Windows, MacOS and Linux based docker installations work differently.
        if system().lower() == "windows":
            docker_path = str(Path.home()) + "C:\\ProgramData\\Docker"
        elif system().lower() == "darwin":
            docker_path = str(Path.home()) + "/Library/Containers/com.docker.docker/Data/vms/0/"
        elif system().lower() == "linux":
            docker_path = "/var/lib/docker"
        usage = shutil.disk_usage(docker_path)
        percentage_used = usage[1] / usage[0]
        if percentage_used >= 0.5:
            logger.warning(
                "%s percent of docker disk space at %s is used. "
                "Please consider freeing up disk space or increasing the EBS volume if you "
                "are on a SageMaker Notebook.",
                percentage_used * 100,
                docker_path,
            )
        else:
            logger.info(
                "%s percent of docker disk space at %s is used.", percentage_used * 100, docker_path
            )
    except Exception as e:  # pylint: disable=W0703
        logger.warning(
            "Unable to check docker volume utilization at the expected path %s. %s",
            docker_path,
            str(e),
        )