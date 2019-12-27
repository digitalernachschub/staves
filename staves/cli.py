"""Installs Gentoo portage packages into a specified directory."""

import logging
import os
from pathlib import Path

import click

from staves.core import Libc, StavesError


logger = logging.getLogger(__name__)


@click.group(name='staves')
@click.option('--log-level', type=click.Choice(['error', 'warning', 'info', 'debug']), default='info')
def cli(log_level: str):
    log_level = logging.getLevelName(log_level.upper())
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)


@cli.command(help='Initializes a builder for the specified runtime')
@click.option('--staves-version')
@click.option('--runtime', type=click.Choice(['docker']), default='docker', show_default=True)
@click.option('--stage3', default='latest', show_default=True)
@click.option('--portage-snapshot', default='latest', show_default=True)
@click.option('--libc', type=click.Choice(['glibc', 'musl']), default='glibc', show_default=True)
def init(staves_version, runtime, stage3, portage_snapshot, libc):
    if runtime == 'docker':
        from staves.runtimes.docker import init
        builder_name = init(staves_version, stage3, portage_snapshot, libc)
        click.echo(builder_name)


@cli.command(help='Installs the specified packages into to the desired location.')
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
@click.option('--builder', help='The name of the builder to be used')
@click.option('--build-cache', help='The name of the cache volume for the Docker runtime')
@click.option('--ssh/--no-ssh', is_flag=True, default=True, help='Use this user\'s ssh identity for the builder')
@click.option('--netrc/--no-netrc', is_flag=True, default=True, help='Use this user\'s netrc configuration in the builder')
@click.option('--locale', default='en_US.UTF-8', help='Specifies the locale (LANG env var) to be set in the builder')
@click.option('--update', multiple=True, help='Repositories to be updated')
def build(version, config, libc, name, rootfs_path, packaging, create_builder, stdlib, jobs, runtime,
          builder, build_cache, ssh, netrc, locale, update):
    config_path = Path(str(config)) if config else Path('staves.toml')
    if not config_path.exists():
        raise StavesError(f'No configuration file found at path "{str(config_path)}"')
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
        if update:
            for repo_name in update:
                args += ['--update', repo_name]
        args.append(version)
        run_docker.run(builder, args, build_cache, config_path, ssh=ssh, netrc=netrc, env={'LANG': locale})
    else:
        from staves.runtimes.core import run
        libc_enum = Libc.musl if 'musl' in libc else Libc.glibc
        with config_path.open(mode='r') as config_file:
            run(config_file, libc_enum, rootfs_path, packaging, version, create_builder, stdlib, name=name, jobs=jobs,
                update_repos=update)


def main():
    cli.main(standalone_mode=False)


if __name__ == '__main__':
    main()
