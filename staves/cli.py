"""Installs Gentoo portage packages into a specified directory."""

import logging
import os
from pathlib import Path

import click

from staves.types import Libc


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)


@click.group(name='staves')
def main():
    pass


@main.command(help='Initializes a builder for the specified runtime')
@click.option('--staves-version')
@click.option('--runtime', type=click.Choice(['docker']))
@click.option('--stage3')
@click.option('--portage-snapshot')
@click.option('--libc', type=click.Choice(['glibc', 'musl']))
def init(staves_version, runtime, stage3, portage_snapshot, libc):
    if runtime == 'docker':
        from staves.runtimes.docker import init
        init(staves_version, stage3, portage_snapshot, libc)


@main.command(help='Installs the specified packages into to the desired location.')
@click.argument('version')
@click.option('--config', type=click.Path(dir_okay=False, exists=True))
@click.option('--libc', type=click.Choice(['glibc', 'musl']), default='glibc', help='Libc to be installed into rootfs')
@click.option('--stdlib', is_flag=True, help='Copy libstdc++ into rootfs')
@click.option('--name', help='Overrides the image name specified in the configuration')
@click.option('--rootfs_path', default=os.path.join('/tmp', 'rootfs'),
              help='Directory where the root filesystem will be installed. Defaults to /tmp/rootfs')
@click.option('--packaging', type=click.Choice(['none', 'docker']), default='docker',
              help='Packaging format of the resulting image')
@click.option('--create-builder', is_flag=True, default=False,
              help='When a builder is created, Staves will copy files such as the Portage tree, make.conf and make.profile.')
@click.option('--jobs', type=int, help='Number of concurrent jobs executed by the builder')
@click.option('--runtime', type=click.Choice(['none', 'docker']), default='docker',
              help='Which environment staves will be executed in')
@click.option('--runtime-docker-builder', help='The name of the builder image')
@click.option('--runtime-docker-build-cache', help='The name of the cache volume')
@click.option('--ssh/--no-ssh', is_flag=True, default=True, help='Use this user\'s ssh identity for the builder')
@click.option('--netrc/--no-netrc', is_flag=True, default=True, help='Use this user\'s netrc configuration in the builder')
def build(version, config, libc, name, rootfs_path, packaging, create_builder, stdlib, jobs, runtime,
          runtime_docker_builder, runtime_docker_build_cache, ssh, netrc):
    config_path = Path(str(config)) if config else Path('staves.toml')
    if runtime == 'docker':
        import staves.runtimes.docker as run_docker
        args = ['build', '--libc', libc, '--rootfs_path', rootfs_path, '--packaging', packaging]
        if stdlib:
            args += ['--stdlib']
        if create_builder:
            args += ['--create-builder']
        if name:
            args += ['--name', name]
        if jobs:
            args += ['--jobs', str(jobs)]
        args += ['--runtime', 'none']
        args.append(version)
        run_docker.run(runtime_docker_builder, args, runtime_docker_build_cache, config_path, ssh=ssh,
                       netrc=netrc)
    else:
        from staves.runtimes.core import run
        libc_enum = Libc.musl if 'musl' in libc else Libc.glibc
        with config_path.open(mode='r') as config_file:
            run(config_file, libc_enum, rootfs_path, packaging, version, create_builder, stdlib, name=name, jobs=jobs)


if __name__ == '__main__':
    main()
