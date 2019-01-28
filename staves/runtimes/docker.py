from typing import IO, Sequence

import subprocess


def init(version: str, stage3: str, portage_snapshot: str, libc: str) -> str:
    image_name = f'staves/bootstrap-x86_64-{libc}:{version}'
    command = ['docker', 'build', '--tag', image_name, '--no-cache',
               '-f', f'Dockerfile.x86_64-{libc}', '--build-arg', f'STAGE3={stage3}',
               '--build-arg', f'PORTAGE_SNAPSHOT={portage_snapshot}', '.']
    subprocess.run(command)
    return image_name


def run(builder: str, args: Sequence[str], build_cache: str, config_file: IO, ssh: bool=False, netrc: bool=False):
    command = [
        'docker', 'run', '--rm', '--interactive',
        '--mount', f'type=volume,source={build_cache},target=/usr/portage/packages',
        '--mount', 'type=bind,source=/run/docker.sock,target=/var/run/docker.sock'
    ]
    if ssh:
        command += [
            '--mount', 'type=bind,source=${HOME}/.ssh,target=/root/.ssh,readonly',
            '--mount', 'type=bind,source=${HOME}/.ssh,target=/var/tmp/portage/.ssh,readonly'
        ]
    if netrc:
        command += [
            '--mount', 'type=bind,source=${HOME}/.netrc,target=/root/.netrc,readonly',
            '--mount', 'type=bind,source=${HOME}/.netrc,target=/var/tmp/portage/.netrc,readonly'
        ]
    command += [builder, *args]
    subprocess.run(command , stdin=config_file)
