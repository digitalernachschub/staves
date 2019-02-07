import logging
import subprocess
import sys
from pathlib import Path
from typing import Mapping, MutableSequence

import docker
from docker.types import Mount

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def init(version: str, stage3: str, portage_snapshot: str, libc: str) -> str:
    image_name = f'staves/bootstrap-x86_64-{libc}:{version}'
    command = ['docker', 'build', '--pull', '--tag', image_name, '--no-cache',
               '-f', f'Dockerfile.x86_64-{libc}', '--build-arg', f'STAGE3={stage3}',
               '--build-arg', f'PORTAGE_SNAPSHOT={portage_snapshot}', '.']
    docker_call = subprocess.run(command, stdout=subprocess.PIPE, universal_newlines=True)
    print(docker_call.stdout, file=sys.stderr, flush=True)
    docker_call.check_returncode()
    return image_name


def run(builder: str, args: MutableSequence[str], build_cache: str, config: Path, ssh: bool=False, netrc: bool=False,
        env: Mapping[str, str]=None):
    docker_client = docker.from_env()
    args.insert(-1, '--config')
    args.insert(-1, '/staves.toml')
    mounts = [
        Mount(type='volume', source=build_cache, target='/usr/portage/packages',),
        Mount(type='bind', source='/run/docker.sock', target='/var/run/docker.sock'),
        Mount(type='bind', source=str(config.resolve()), target='/staves.toml', read_only=True)
    ]
    if ssh:
        ssh_dir = str(Path.home().joinpath('.ssh'))
        mounts += [
            Mount(type='bind', source=ssh_dir, target='/root/.ssh', read_only=True),
            Mount(type='bind', source=ssh_dir, target='/var/tmp/portage/.ssh', read_only=True)
        ]
    if netrc:
        netrc_path = str(Path.home().joinpath('.ssh'))
        mounts += [
            Mount(type='bind', source=netrc_path, target='/root/.netrc', read_only=True),
            Mount(type='bind', source=netrc_path, target='/var/tmp/portage/.netrc', read_only=True)
        ]
    logger.debug('Starting docker container with the following mounts:')
    for mount in mounts:
        logger.debug(str(mount))
    container = docker_client.containers.run(builder, command=args, auto_remove=True, mounts=mounts, detach=True,
                                             environment=env)
    for line in container.logs(stream=True):
        print(line.decode(), end='')
