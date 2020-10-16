import io
import json
import logging
import os
import socket
import struct
import subprocess
import sys
import tarfile
from dataclasses import asdict
from pathlib import Path
from typing import Mapping

import docker
from docker.types import Mount

import staves.builders.gentoo as gentoo_builder
from staves.builders.gentoo import BuilderConfig, Libc, ImageSpec

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def run(
    builder: str,
    portage: str,
    build_cache: str,
    image_spec: ImageSpec,
    stdlib: bool = False,
    ssh: bool = False,
    netrc: bool = False,
    env: Mapping[str, str] = None,
):
    docker_client = docker.from_env()

    mounts = [
        Mount(
            type="volume",
            source=build_cache,
            target="/var/cache/binpkgs",
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
    portage_container = docker_client.containers.create(
        portage,
        auto_remove=True,
    )
    args = []
    if stdlib:
        args += ["--stdlib"]
    container = docker_client.containers.create(
        builder,
        entrypoint=["/usr/bin/python", "/staves.py"],
        command=args,
        auto_remove=True,
        mounts=mounts,
        detach=True,
        environment=env,
        stdin_open=True,
        volumes_from=[portage_container.id + ":ro"],
    )
    bundle_file = io.BytesIO()
    with tarfile.TarFile(fileobj=bundle_file, mode="x") as archive:
        builder_runtime_path = os.path.abspath(gentoo_builder.__file__)
        archive.add(builder_runtime_path, arcname="staves.py")
    bundle_file.seek(0)
    bundle_content = bundle_file.read()
    container.put_archive("/", bundle_content)
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
