import subprocess
import tempfile
from typing import MutableSequence

import docker
from docker.types import Mount


def init(version: str, stage3: str, portage_snapshot: str, libc: str) -> str:
    image_name = f'staves/bootstrap-x86_64-{libc}:{version}'
    command = ['docker', 'build', '--tag', image_name, '--no-cache',
               '-f', f'Dockerfile.x86_64-{libc}', '--build-arg', f'STAGE3={stage3}',
               '--build-arg', f'PORTAGE_SNAPSHOT={portage_snapshot}', '.']
    subprocess.run(command)
    return image_name


def run(builder: str, args: MutableSequence[str], build_cache: str, config: str, ssh: bool=False, netrc: bool=False):
    docker_client = docker.from_env()
    with tempfile.NamedTemporaryFile(mode='w') as config_file:
        print(config_file.name)
        print(config, flush=True)
        config_file.write(config)
        args.insert(-1, '--config')
        args.insert(-1, '/staves.toml')
        mounts = [
            Mount(type='volume', source=build_cache, target='/usr/portage/packages',),
            Mount(type='bind', source='/run/docker.sock', target='/var/run/docker.sock'),
            Mount(type='bind', source=config_file.name, target='/staves.toml', read_only=True)
        ]
        if ssh:
            mounts += [
                Mount(type='bind', source='${HOME}/.ssh', target='/root/.ssh', read_only=True),
                Mount(type='bind', source='${HOME}/.ssh', target='/var/tmp/portage/.ssh', read_only=True)
            ]
        if netrc:
            mounts += [
                Mount(type='bind', source='${HOME}/.netrc', target='/root/.netrc', read_only=True),
                Mount(type='bind', source='${HOME}/.netrc', target='/var/tmp/portage/.netrc', read_only=True)
            ]
        docker_client.containers.run(builder, command=args, auto_remove=True, mounts=mounts)
