import glob
import multiprocessing
import os
import shutil
import subprocess

import click


class StavesError(Exception):
    pass


class RootfsError(Exception):
    pass


def _create_rootfs(rootfs_path, *packages, max_concurrent_jobs: int=1, max_cpu_load: int=1):
    click.echo('Creating rootfs at {} containing the following packages:'.format(rootfs_path))
    click.echo(', '.join(packages))

    click.echo('Installing build-time dependencies to builder')
    emerge_env = os.environ
    emerge_env['MAKEOPTS'] = '-j{} -l{}'.format(max_concurrent_jobs, max_cpu_load)
    # --emptytree is needed, because build dependencies of runtime dependencies are ignored by --root-deps=rdeps
    # (even when --with-bdeps=y is passed). By adding --emptytree, we get a binary package that can be installed to rootfs
    emerge_bdeps_command = ['emerge', '--verbose', '--onlydeps', '--usepkg', '--with-bdeps=y', '--emptytree',
                            '--jobs', str(max_concurrent_jobs), '--load-average', str(max_cpu_load), *packages]
    emerge_bdeps_call = subprocess.run(emerge_bdeps_command, stderr=subprocess.PIPE, env=emerge_env)
    if emerge_bdeps_call.returncode != 0:
        click.echo(emerge_bdeps_call.stderr, err=True)
        raise RootfsError('Unable to install build-time dependencies.')

    click.echo('Installing runtime dependencies to rootfs')
    emerge_rdeps_command = ['emerge', '--verbose', '--root={}'.format(rootfs_path), '--root-deps=rdeps', '--oneshot',
                            '--usepkg', '--jobs', str(max_concurrent_jobs), '--load-average', str(max_cpu_load), *packages]
    emerge_rdeps_call = subprocess.run(emerge_rdeps_command, stderr=subprocess.PIPE, env=emerge_env)
    if emerge_rdeps_call.returncode != 0:
        click.echo(emerge_rdeps_call.stderr, err=True)
        raise RootfsError('Unable to install runtime dependencies.')


def _max_cpu_load() -> int:
    return multiprocessing.cpu_count()


def _max_concurrent_jobs() -> int:
    return _max_cpu_load() + 1


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
        with open(package_config_path, 'w') as f:
            package_environments = ' '.join(env)
            f.write('{} {}{}'.format(package, package_environments, os.linesep))
    if keywords:
        package_config_path = os.path.join('/etc', 'portage', 'package.accept_keywords', *package.split('/'))
        os.makedirs(os.path.dirname(package_config_path), exist_ok=True)
        with open(package_config_path, 'w') as f:
            package_keywords = ' '.join(keywords)
            f.write('{} {}{}'.format(package, package_keywords, os.linesep))
    if use:
        package_config_path = os.path.join('/etc', 'portage', 'package.use', *package.split('/'))
        os.makedirs(os.path.dirname(package_config_path), exist_ok=True)
        with open(package_config_path, 'w') as f:
            package_use_flags = ' '.join(use)
            f.write('{} {}{}'.format(package, package_use_flags, os.linesep))


def _copy_stdlib(rootfs_path: str, copy_libstdcpp: bool):
    libgcc = 'libgcc_s.so.1'
    libstdcpp = 'libstdc++.so.6'
    search_path = os.path.join('/usr', 'lib', 'gcc')
    libgcc_path = None
    libstdcpp_path = None
    for directory_path, subdirs, files in os.walk(search_path):
        if libgcc in files:
            libgcc_path = os.path.join(directory_path, libgcc)
        if libstdcpp in files:
            libstdcpp_path = os.path.join(directory_path, libstdcpp)
    if libgcc_path is None:
        raise StavesError('Unable to find ' + libgcc + ' in ' + search_path)
    shutil.copy(libgcc_path, os.path.join(rootfs_path, 'usr', 'lib'))
    if copy_libstdcpp:
        if libstdcpp_path is None:
            raise StavesError('Unable to find ' + libstdcpp + ' in ' + search_path)
        shutil.copy(libstdcpp_path, os.path.join(rootfs_path, 'usr', 'lib'))


def _add_repository(name: str, sync_type: str=None, uri: str=None):
    if uri and sync_type:
        subprocess.run(['eselect', 'repository', 'add', name, sync_type, uri], stderr=subprocess.PIPE)
    else:
        subprocess.run(['eselect', 'repository', 'enable', name], stderr=subprocess.PIPE)
    subprocess.run(['emaint', 'sync', '--repo', name], stderr=subprocess.PIPE)


def _update_builder(max_concurrent_jobs: int=1, max_cpu_load: int=1):
    # Register staves in /var/lib/portage/world
    register_staves = subprocess.run(['emerge', '--noreplace', 'dev-util/staves'], stderr=subprocess.PIPE)
    if register_staves.returncode != 0:
        click.echo(register_staves.stderr, err=True)
        raise RootfsError('Unable to register Staves as an installed package')

    emerge_env = os.environ
    emerge_env['MAKEOPTS'] = '-j{} -l{}'.format(max_concurrent_jobs, max_cpu_load)
    update_world = subprocess.run(['emerge', '--verbose', '--deep', '--usepkg', '--with-bdeps=y', '--jobs', str(max_concurrent_jobs),
                                   '--load-average', str(max_cpu_load), '@world'], stderr=subprocess.PIPE, env=emerge_env)
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