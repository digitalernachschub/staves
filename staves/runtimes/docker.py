from typing import Sequence

import subprocess


def run(builder: str, args: Sequence[str], build_cache: str, config_content: str, ssh: bool=False):
    command = ['docker', 'run', '--rm', '--interactive',
               '--mount', f'type=volume,source={build_cache},target=/usr/portage/packages',
               '--mount', 'type=bind,source=/run/docker.sock,target=/var/run/docker.sock',
               builder, *args]
    if ssh:
        command += [
            '--mount', 'type=bind,source=${HOME}/.ssh,target=/root/.ssh,readonly',
            '--mount', 'type=bind,source=${HOME}/.ssh,target=/var/tmp/portage/.ssh,readonly'
        ]
    subprocess.run(command , shell=True, input=config_content)
