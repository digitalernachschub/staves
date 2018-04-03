"""Installs Gentoo portage packages into a specified directory."""

import click
import io
import glob
import os
import shutil
import subprocess
import tarfile

import docker
import toml


class StavesError(Exception):
    pass


class RootfsError(Exception):
    pass


def _create_rootfs(rootfs_path, *packages):
    click.echo('Creating rootfs at {} containing the following packages:'.format(rootfs_path))
    click.echo(', '.join(packages))

    click.echo('Installing build-time dependencies to builder')
    emerge_bdeps_command = ['emerge', '--verbose', '--onlydeps', '--onlydeps-with-rdeps=n',
                            '--usepkg', '--with-bdeps=y', *packages]
    emerge_bdeps_call = subprocess.run(emerge_bdeps_command, stderr=subprocess.PIPE)
    if emerge_bdeps_call.returncode != 0:
        click.echo(emerge_bdeps_call.stderr, err=True)
        raise RootfsError('Unable to install build-time dependencies.')

    click.echo('Installing runtime dependencies to rootfs')
    emerge_rdeps_command = ['emerge', '--verbose', '--root={}'.format(rootfs_path), '--root-deps=rdeps', '--oneshot',
                            '--usepkg', *packages]
    emerge_rdeps_call = subprocess.run(emerge_rdeps_command, stderr=subprocess.PIPE)
    if emerge_rdeps_call.returncode != 0:
        click.echo(emerge_rdeps_call.stderr, err=True)
        raise RootfsError('Unable to install runtime dependencies.')


def _create_dockerfile(*cmd: str) -> str:
    command_string = ', '.join(['\"{}\"'.format(c) for c in cmd])
    return """\
    FROM scratch
    COPY rootfs /
    ENTRYPOINT [{}]
    """.format(command_string)


def _docker_image_from_rootfs(rootfs_path: str, tag: str, command: list):
    client = docker.from_env()
    dockerfile = _create_dockerfile(*command).encode('utf-8')
    context = io.BytesIO()
    with tarfile.open(fileobj=context, mode='w') as tar:
        dockerfile_info = tarfile.TarInfo(name="Dockerfile")
        dockerfile_info.size = len(dockerfile)
        tar.addfile(dockerfile_info, fileobj=io.BytesIO(dockerfile))
        tar.add(name=rootfs_path, arcname='rootfs')
    context.seek(0)
    client.images.build(fileobj=context, tag=tag, custom_context=True)


def _write_env(env_vars, name=None):
    os.makedirs('/etc/portage/env', exist_ok=True)
    if name:
        conf_path = os.path.join('/etc', 'portage', 'env', name)
    else:
        conf_path = os.path.join('/etc', 'portage', 'make.conf')
    with open(conf_path, 'a') as make_conf:
        make_conf.writelines(('{}="{}"{}'.format(k, v, os.linesep) for k, v in env_vars.items()))


def _write_package_config(package: str, env: list=None, keywords: list=None, use: list=None):
    if env:
        package_config_path = os.path.join('/etc', 'portage', 'package.env', *package.split('/'))
        os.makedirs(os.path.dirname(package_config_path), exist_ok=True)
        with open(package_config_path, 'a') as f:
            package_environments = ' '.join(env)
            f.write('{} {}{}'.format(package, package_environments, os.linesep))
    if keywords:
        package_config_path = os.path.join('/etc', 'portage', 'package.accept_keywords', *package.split('/'))
        os.makedirs(os.path.dirname(package_config_path), exist_ok=True)
        with open(package_config_path, 'a') as f:
            package_keywords = ' '.join(keywords)
            f.write('{} {}{}'.format(package, package_keywords, os.linesep))
    if use:
        package_config_path = os.path.join('/etc', 'portage', 'package.use', *package.split('/'))
        os.makedirs(os.path.dirname(package_config_path), exist_ok=True)
        with open(package_config_path, 'a') as f:
            package_use_flags = ' '.join(use)
            f.write('{} {}{}'.format(package, package_use_flags, os.linesep))


def _copy_stdlib(rootfs_path: str):
    for directory_path, subdirs, files in os.walk(os.path.join('/usr', 'lib', 'gcc', 'x86_64-pc-linux-gnu')):
        if 'libgcc_s.so.1' in files:
            shutil.copy(os.path.join(directory_path, 'libgcc_s.so.1'), os.path.join(rootfs_path, 'usr', 'lib'))


def _add_repository(name: str, sync_type: str=None, uri: str=None):
    if uri and sync_type:
        subprocess.run(['eselect', 'repository', 'add', name, sync_type, uri], stderr=subprocess.PIPE)
    else:
        subprocess.run(['eselect', 'repository', 'enable', name], stderr=subprocess.PIPE)
    subprocess.run(['emaint', 'sync', '--repo', name], stderr=subprocess.PIPE)


def _update_builder():
    # Register staves in /var/lib/portage/world
    register_staves = subprocess.run(['emerge', '--noreplace', 'dev-util/staves'], stderr=subprocess.PIPE)
    if register_staves.returncode != 0:
        click.echo(register_staves.stderr, err=True)
        raise RootfsError('Unable to register Staves as an installed package')
    update_world = subprocess.run(['emerge', '--verbose', '--deep', '--usepkg', '--with-bdeps=y', '@world'], stderr=subprocess.PIPE)
    if update_world.returncode != 0:
        click.echo(update_world.stderr, err=True)
        raise RootfsError('Unable to update builder environment')


def _fix_portage_tree_permissions():
    for directory_path, subdirs, files in os.walk(os.path.join('/usr', 'portage')):
        for subdir in subdirs:
            shutil.chown(os.path.join(directory_path, subdir), user='portage', group='portage')
        for f in files:
            shutil.chown(os.path.join(directory_path, f), user='portage', group='portage')


def _copy_to_rootfs(rootfs, path):
    globs = glob.iglob(path)
    for host_path in globs:
        rootfs_path = os.path.join(rootfs, os.path.relpath(host_path, '/'))
        os.makedirs(os.path.dirname(rootfs_path), exist_ok=True)
        if os.path.islink(host_path): # Needs to be checked first, because other methods follow links
            link_target = os.readlink(host_path)
            os.symlink(link_target, rootfs_path)
        elif os.path.isdir(host_path):
            shutil.copytree(host_path, rootfs_path)
        elif os.path.isfile(host_path):
            shutil.copy(host_path, rootfs_path)
        else:
            raise StavesError('Copying {} to rootfs is not supported.'.format(path))


@click.command(help='Installs the specified packages into to the desired location.')
@click.argument('version')
@click.option('--libc', envvar='STAVES_LIBC', default='', help='Libc to be installed into rootfs')
@click.option('--name', help='Overrides the image name specified in the configuration')
@click.option('--rootfs_path', default=os.path.join('/tmp', 'rootfs'),
              help='Directory where the root filesystem will be installed. Defaults to /tmp/rootfs')
@click.option('--packaging', type=click.Choice(['none', 'docker']), default='docker',
              help='Packaging format of the resulting image')
@click.option('--create-builder', is_flag=True, default=False,
              help='When a builder is created, Staves will copy files such as the Portage tree, make.conf and make.profile.')
def main(version, libc, name, rootfs_path, packaging, create_builder):
    config = toml.load(click.get_text_stream('stdin'))
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
        _update_builder()
    _create_rootfs(rootfs_path, *packages_to_be_installed)
    _copy_stdlib(rootfs_path)
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
            '/var/db/repos/*'
        ]
        for f in builder_files:
            _copy_to_rootfs(rootfs_path, f)
    tag = '{}:{}'.format(name, version)
    if packaging == 'docker':
        _docker_image_from_rootfs(rootfs_path, tag, config['command'])


if __name__ == '__main__':
    main()
