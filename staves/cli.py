"""Installs Gentoo portage packages into a specified directory."""

import io
import os
import subprocess
import sys
import tarfile
from typing import Mapping

import click
import docker
import toml

from staves.builders.gentoo import _create_rootfs, _max_cpu_load, _max_concurrent_jobs, _write_env, \
    _write_package_config, _copy_stdlib, _add_repository, _update_builder, _fix_portage_tree_permissions, \
    _copy_to_rootfs


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
    if 'env' in config:
        make_conf_vars = {k: v for k, v in config['env'].items() if not isinstance(v, dict)}
        _write_env(make_conf_vars)
        specialized_envs = {k: v for k, v in config['env'].items() if k not in make_conf_vars}
        for env_name, env in specialized_envs.items():
            _write_env(name=env_name, env_vars=env)
        config.pop('env')
    if 'repositories' in config:
        os.makedirs('/etc/portage/repos.conf', exist_ok=True)
        subprocess.run(['eselect', 'repository', 'list', '-i'], stderr=subprocess.PIPE)
        for repository in config.pop('repositories'):
            _add_repository(repository['name'], sync_type=repository.get('type'), uri=repository.get('uri'))
    locale = config.pop('locale') if 'locale' in config else {'name': 'C', 'charset': 'UTF-8'}
    package_configs = {k: v for k, v in config.items() if isinstance(v, dict)}
    for package, package_config in package_configs.items():
        _write_package_config(package, **package_config)
    packages_to_be_installed = [*config.get('packages', [])]
    if libc:
        packages_to_be_installed.append(libc)
    if 'musl' not in libc:
        # This value should depend on the selected profile, but there is currently no musl profile with
        # links to lib directories.
        for prefix in ['', 'usr', 'usr/local']:
            lib_prefix = os.path.join(rootfs_path, prefix)
            lib_path = os.path.join(lib_prefix, 'lib64')
            os.makedirs(lib_path, exist_ok=True)
            os.symlink('lib64', os.path.join(lib_prefix, 'lib'))
    if os.path.exists(os.path.join('/usr', 'portage')):
        _fix_portage_tree_permissions()
    if create_builder:
        _update_builder(max_concurrent_jobs=_max_concurrent_jobs(), max_cpu_load=_max_cpu_load())
    _create_rootfs(rootfs_path, *packages_to_be_installed, max_concurrent_jobs=_max_concurrent_jobs(), max_cpu_load=_max_cpu_load())
    _copy_stdlib(rootfs_path, copy_libstdcpp=stdlib)
    if 'glibc' in libc:
        with open(os.path.join('/etc', 'locale.gen'), 'a') as locale_conf:
            locale_conf.writelines('{} {}'.format(locale['name'], locale['charset']))
            subprocess.run('locale-gen')
        _copy_to_rootfs(rootfs_path, '/usr/lib/locale/locale-archive')
    if create_builder:
        builder_files = [
            '/usr/portage',
            '/etc/portage/make.conf',
            '/etc/portage/make.profile',
            '/etc/portage/repos.conf',
            '/etc/portage/env',
            '/etc/portage/package.env',
            '/etc/portage/package.use',
            '/etc/portage/package.accept_keywords',
            '/var/db/repos/*'
        ]
        for f in builder_files:
            _copy_to_rootfs(rootfs_path, f)
    tag = '{}:{}'.format(name, version)
    if packaging == 'docker':
        _docker_image_from_rootfs(rootfs_path, tag, config['command'], config.get('annotations', {}))


if __name__ == '__main__':
    main()
