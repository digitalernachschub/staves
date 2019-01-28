"""Installs Gentoo portage packages into a specified directory."""

import io
import os
import sys
import tarfile
from typing import Mapping

import click
import docker


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
@click.option('--config', type=click.File())
@click.option('--libc', envvar='STAVES_LIBC', default='', help='Libc to be installed into rootfs')
@click.option('--stdlib', is_flag=True, help='Copy libstdc++ into rootfs')
@click.option('--name', help='Overrides the image name specified in the configuration')
@click.option('--rootfs_path', default=os.path.join('/tmp', 'rootfs'),
              help='Directory where the root filesystem will be installed. Defaults to /tmp/rootfs')
@click.option('--packaging', type=click.Choice(['none', 'docker']), default='docker',
              help='Packaging format of the resulting image')
@click.option('--create-builder', is_flag=True, default=False,
              help='When a builder is created, Staves will copy files such as the Portage tree, make.conf and make.profile.')
@click.option('--jobs', type=int, help='Number of concurrent jobs executed by the builder')
@click.option('--runtime', type=click.Choice(['none', 'docker']), default='none',
              help='Which environment staves will be executed in')
@click.option('--runtime-docker-builder', help='The name of the builder image')
@click.option('--runtime-docker-build-cache', help='The name of the cache volume')
@click.option('--runtime-docker-ssh', is_flag=True, default=False, help='Use this user\'s ssh identity for the builder')
@click.option('--runtime-docker-netrc', is_flag=True, default=False, help='Use this user\'s netrc configuration in the builder')
def build(version, config, libc, name, rootfs_path, packaging, create_builder, stdlib, jobs, runtime,
          runtime_docker_builder, runtime_docker_build_cache, runtime_docker_ssh, runtime_docker_netrc):
    if not config:
        config = click.get_text_stream('stdin')
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
        args.append(version)
        run_docker.run(runtime_docker_builder, args, runtime_docker_build_cache, config.read(), ssh=runtime_docker_ssh,
                       netrc=runtime_docker_netrc)
    else:
        from staves.runtimes.core import run
        run(config, libc, rootfs_path, packaging, version, create_builder, stdlib, name=name, jobs=jobs)


if __name__ == '__main__':
    main()



