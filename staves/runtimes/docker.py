import json
import logging
import socket
import struct
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Mapping

import docker
from docker.types import Mount

from staves.builders.gentoo import BuilderConfig, Libc, ImageSpec

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def bootstrap(version: str, stage3: str, portage_snapshot: str, libc: str) -> str:
    image_name = f"staves/bootstrap-x86_64-{libc}:{version}"
    command = [
        "docker",
        "build",
        "--pull",
        "--tag",
        image_name,
        "--no-cache",
        "-f",
        f"Dockerfile.x86_64-{libc}",
        "--build-arg",
        f"STAGE3={stage3}",
        "--build-arg",
        f"PORTAGE_SNAPSHOT={portage_snapshot}",
        ".",
    ]
    docker_call = subprocess.run(
        command, stdout=subprocess.PIPE, universal_newlines=True
    )
    print(docker_call.stdout, file=sys.stderr, flush=True)
    docker_call.check_returncode()
    return image_name


def run(
    builder: str,
    builder_config: BuilderConfig,
    stdlib: bool,
    create_builder: bool,
    build_cache: str,
    image_spec: ImageSpec,
    ssh: bool = False,
    netrc: bool = False,
    env: Mapping[str, str] = None,
):
    docker_client = docker.from_env()
    args = ["build"]
    if stdlib:
        args += ["--stdlib"]
    if create_builder:
        args += ["--create-builder"]
    args += ["--config", "-"]
    args += ["--libc", "musl" if builder_config.libc == Libc.musl else "glibc"]
    args += ["--runtime", "none"]
    if builder_config.concurrent_jobs:
        args += ["--jobs", str(builder_config.concurrent_jobs)]

    mounts = [
        Mount(
            type="volume",
            source=build_cache,
            target="/usr/portage/packages",
        ),
    ]
    if ssh:
        ssh_dir = str(Path.home().joinpath(".ssh"))
        mounts += [
            Mount(type="bind", source=ssh_dir, target="/root/.ssh", read_only=True),
            Mount(
                type="bind",
                source=ssh_dir,
                target="/var/tmp/portage/.ssh",
                read_only=True,
            ),
        ]
    if netrc:
        netrc_path = str(Path.home().joinpath(".ssh"))
        mounts += [
            Mount(
                type="bind", source=netrc_path, target="/root/.netrc", read_only=True
            ),
            Mount(
                type="bind",
                source=netrc_path,
                target="/var/tmp/portage/.netrc",
                read_only=True,
            ),
        ]
    logger.debug("Starting docker container with the following mounts:")
    for mount in mounts:
        logger.debug(str(mount))
    container = docker_client.containers.create(
        builder,
        entrypoint=["/usr/bin/python", "-m", "staves.builders.gentoo"],
        auto_remove=True,
        mounts=mounts,
        detach=True,
        environment=env,
        stdin_open=True,
    )
    container.start()
    container_input = container.attach_socket(params={"stdin": 1, "stream": 1})
    serialized_image_spec = json.dumps(
        dict(
            locale=asdict(image_spec.locale),
            global_env=image_spec.global_env,
            package_envs=image_spec.package_envs,
            repositories=[asdict(repository) for repository in image_spec.repositories],
            package_configs=image_spec.package_configs,
            packages_to_be_installed=image_spec.packages_to_be_installed,
        )
    ).encode()
    content_length = struct.pack(">Q", len(serialized_image_spec))
    content = content_length + serialized_image_spec
    container_input._sock.send(content)
    container_input._sock.shutdown(socket.SHUT_RDWR)
    container_input.close()
    for line in container.logs(stream=True):
        print(line.decode(), end="")
