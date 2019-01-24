"""Installs Gentoo portage packages into a specified directory."""

import io
import os
import sys
import tarfile
from typing import Mapping

import click
import docker
import toml

from staves.builders.gentoo import build


def _create_dockerfile(annotations: Mapping[str, str], *cmd: str) -> str:
    label_string = ' '.join([f'"{key}"="{value}"' for key, value in annotations.items()])
    command_string = ', '.join(['\"{}\"'.format(c) for c in cmd])
    dockerfile = ''
    if label_string:
        dockerfile += 'LABEL {label_string}' + os.linesep
    dockerfile += f"""\
    FROM scratch
    COPY rootfs /
    ENTRYPOINT [{command_string}]
    """
    return dockerfile


def _docker_image_from_rootfs(rootfs_path: str, tag: str, command: list, annotations: Mapping[str, str]):
    client = docker.from_env()
    dockerfile = _create_dockerfile(annotations, *command).encode('utf-8')
    context = io.BytesIO()
    with tarfile.open(fileobj=context, mode='w') as tar:
        dockerfile_info = tarfile.TarInfo(name="Dockerfile")
        dockerfile_info.size = len(dockerfile)
        tar.addfile(dockerfile_info, fileobj=io.BytesIO(dockerfile))
        tar.add(name=rootfs_path, arcname='rootfs')
    context.seek(0)
    client.images.build(fileobj=context, tag=tag, custom_context=True)


@click.command(help='Installs the specified packages into to the desired location.')
@click.argument('version')
@click.option('--libc', envvar='STAVES_LIBC', default='', help='Libc to be installed into rootfs')
@click.option('--stdlib', is_flag=True, help='Copy libstdc++ into rootfs')
@click.option('--name', help='Overrides the image name specified in the configuration')
@click.option('--rootfs_path', default=os.path.join('/tmp', 'rootfs'),
              help='Directory where the root filesystem will be installed. Defaults to /tmp/rootfs')
@click.option('--packaging', type=click.Choice(['none', 'docker']), default='docker',
              help='Packaging format of the resulting image')
@click.option('--create-builder', is_flag=True, default=False,
              help='When a builder is created, Staves will copy files such as the Portage tree, make.conf and make.profile.')
@click.option('--runtime', type=click.Choice(['none', 'docker']), default='none',
              help='Which environment staves will be executed in')
@click.option('--runtime-docker-builder', help='The name of the builder image')
@click.option('--runtime-docker-build-cache', help='The name of the cache volume')
@click.option('--runtime-docker-ssh', is_flag=True, default=False, help='Use this user\'s ssh identity for the builder')
@click.option('--runtime-docker-netrc', is_flag=True, default=False, help='Use this user\'s netrc configuration in the builder')
def main(version, libc, name, rootfs_path, packaging, create_builder, stdlib, runtime, runtime_docker_builder,
         runtime_docker_build_cache, runtime_docker_ssh, runtime_docker_netrc):
    config_file = click.get_text_stream('stdin')
    if runtime == 'docker':
        import staves.runtimes.docker as run_docker
        args = ['--libc', libc, '--rootfs_path', rootfs_path, '--packaging', packaging]
        if stdlib:
            args += ['--stdlib']
        if create_builder:
            args += ['--create-builder']
        if name:
            args += ['--name', name]
        args.append(version)
        run_docker.run(runtime_docker_builder, args, runtime_docker_build_cache, config_file, ssh=runtime_docker_ssh,
                       netrc=runtime_docker_netrc)
        sys.exit(0)
    config = toml.load(config_file)
    if not name:
        name = config['name']
    env = config.pop('env')
    repositories = config.pop('repositories')
    locale = config.pop('locale') if 'locale' in config else {'name': 'C', 'charset': 'UTF-8'}
    package_configs = {k: v for k, v in config.items() if isinstance(v, dict)}
    packages_to_be_installed = [*config.get('packages', [])]
    build(name, locale, package_configs, packages_to_be_installed, libc, rootfs_path, packaging, version, create_builder,
          stdlib, annotations=config.get('annotations', {}), env=env, repositories=repositories, command=config['command'])


if __name__ == '__main__':
    main()



