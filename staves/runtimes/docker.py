from typing import Sequence

import subprocess


def run(builder: str, args: Sequence[str], build_cache: str, config_content: str):
    subprocess.run(['docker', 'run', '--rm', '--interactive',
                    '--mount', f'type=volume,source={build_cache},target=/usr/portage/packages',
                    '--mount', 'type=bind,source=/run/docker.sock,target=/var/run/docker.sock',
                    builder, *args], shell=True, input=config_content)
