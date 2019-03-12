import glob
import logging
import multiprocessing
import os
import re
import shutil
import subprocess

from typing import Mapping, MutableSequence, Optional, Sequence, NamedTuple

from staves.core import Libc, StavesError


logger = logging.getLogger(__name__)


class RootfsError(StavesError):
    pass


def _create_rootfs(rootfs_path, *packages, max_concurrent_jobs: int=1, max_cpu_load: int=1):
    logger.info('Creating rootfs at {} containing the following packages:'.format(rootfs_path))
    logger.info(', '.join(packages))

    logger.debug('Installing build-time dependencies to builder')
    emerge_env = os.environ
    emerge_env['MAKEOPTS'] = '-j{} -l{}'.format(max_concurrent_jobs, max_cpu_load)
    # --emptytree is needed, because build dependencies of runtime dependencies are ignored by --root-deps=rdeps
    # (even when --with-bdeps=y is passed). By adding --emptytree, we get a binary package that can be installed to rootfs
    emerge_bdeps_command = ['emerge', '--verbose', '--onlydeps', '--usepkg', '--with-bdeps=y', '--emptytree',
                            '--jobs', str(max_concurrent_jobs), '--load-average', str(max_cpu_load), *packages]
    emerge_bdeps_call = subprocess.run(emerge_bdeps_command, stderr=subprocess.PIPE, env=emerge_env)
    if emerge_bdeps_call.returncode != 0:
        logger.error(emerge_bdeps_call.stderr)
        raise RootfsError('Unable to install build-time dependencies.')

    logger.debug('Installing runtime dependencies to rootfs')
    emerge_rdeps_command = ['emerge', '--verbose', '--root={}'.format(rootfs_path), '--root-deps=rdeps', '--oneshot',
                            '--usepkg', '--jobs', str(max_concurrent_jobs), '--load-average', str(max_cpu_load), *packages]
    emerge_rdeps_call = subprocess.run(emerge_rdeps_command, stderr=subprocess.PIPE, env=emerge_env)
    if emerge_rdeps_call.returncode != 0:
        logger.error(emerge_rdeps_call.stderr)
        raise RootfsError('Unable to install runtime dependencies.')


def _max_cpu_load() -> int:
    return multiprocessing.cpu_count()


def _max_concurrent_jobs() -> int:
    return _max_cpu_load() + 1


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


def _update_builder(max_concurrent_jobs: int=1, max_cpu_load: int=1):
    # Register staves in /var/lib/portage/world
    register_staves = subprocess.run(['emerge', '--noreplace', 'dev-util/staves'], stderr=subprocess.PIPE)
    if register_staves.returncode != 0:
        logger.error(register_staves.stderr)
        raise RootfsError('Unable to register Staves as an installed package')

    emerge_env = os.environ
    emerge_env['MAKEOPTS'] = '-j{} -l{}'.format(max_concurrent_jobs, max_cpu_load)
    update_world = subprocess.run(['emerge', '--verbose', '--deep', '--usepkg', '--with-bdeps=y', '--jobs', str(max_concurrent_jobs),
                                   '--load-average', str(max_cpu_load), '@world'], stderr=subprocess.PIPE, env=emerge_env)
    if update_world.returncode != 0:
        logger.error(update_world.stderr)
        raise RootfsError('Unable to update builder environment')


def _fix_portage_tree_permissions():
    for directory_path, subdirs, files in os.walk(os.path.join('/usr', 'portage')):
        for subdir in subdirs:
            shutil.chown(os.path.join(directory_path, subdir), user='portage', group='portage')
        for f in files:
            shutil.chown(os.path.join(directory_path, f), user='portage', group='portage')


def _copy_to_rootfs(rootfs: str, path_glob: str):
    globs = glob.iglob(path_glob)
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
            raise StavesError('Copying {} to rootfs is not supported.'.format(path_glob))


def libc_to_package_name(libc: Libc) -> str:
    if libc == Libc.glibc:
        return 'sys-libs/glibc'
    elif libc == Libc.musl:
        return 'sys-libs/musl'
    else:
        raise ValueError(f'Unsupported value for libc: {libc}')


class Locale(NamedTuple):
    name: str
    charset: str


class Repository(NamedTuple):
    name: str
    sync_type: Optional[str]=None
    uri: Optional[str]=None


def run_and_log_error(cmd: Sequence[str]) -> int:
    update_repos_cmd = subprocess.run(cmd, universal_newlines=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if update_repos_cmd.returncode != 0:
        logger.error(update_repos_cmd.stderr)
        raise StavesError(f'Command failed: {cmd}')
    return update_repos_cmd.returncode


class BuildEnvironment:
    def __init__(self):
        os.makedirs('/etc/portage/repos.conf', exist_ok=True)
        logger.info(f'Updating repository list')
        run_and_log_error(['eselect', 'repository', 'list', '-i'])

    def add_repository(self, name: str, sync_type: str = None, uri: str = None):
        logger.info(f'Adding repository {name}')
        if uri and sync_type:
            add_repo_command = ['eselect', 'repository', 'add', name, sync_type, uri]
        else:
            add_repo_command = ['eselect', 'repository', 'enable', name]
        run_and_log_error(add_repo_command)
        self.update_repository(name)

    def update_repository(self, name: str):
        run_and_log_error(['emaint', 'sync', '--repo', name])

    @property
    def repositories(self) -> Sequence[str]:
        list_repos_call = subprocess.run(['eselect', 'repository', 'list', '-i'], universal_newlines=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if list_repos_call.returncode != 0:
            logger.error(list_repos_call.stderr)
            raise StavesError('Failed to retrieve a list of available repositories')
        repositories = []
        repo_name_pattern = re.compile(r'\s*\[\d+\]\s*(\S+)')
        for line in list_repos_call.stdout.splitlines()[1:]:
            match = repo_name_pattern.match(line)
            if match:
                repositories.append(match.group(1))
        return repositories

    def write_package_config(self, package: str, env: Sequence[str]=None, keywords: Sequence[str]=None, use: Sequence[str]=None):
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

    def write_env(self, env_vars, name=None):
        os.makedirs('/etc/portage/env', exist_ok=True)
        if name:
            conf_path = os.path.join('/etc', 'portage', 'env', name)
        else:
            conf_path = os.path.join('/etc', 'portage', 'make.conf')
        with open(conf_path, 'a') as make_conf:
            make_conf.writelines(('{}="{}"{}'.format(k, v, os.linesep) for k, v in env_vars.items()))


def build(locale: Locale, package_configs: Mapping[str, Mapping], packages: MutableSequence[str],
          libc: Libc, root_path: str, create_builder: bool, stdlib: bool,
          env: Optional[Mapping[str, str]]=None, repositories: Sequence[Repository]=None, max_concurrent_jobs: int=None,
          update_repos: Sequence[str]=None):
    build_env = BuildEnvironment()
    if update_repos:
        for repo_name in update_repos:
            logger.info(f'Updating repository "{repo_name}"…')
            build_env.update_repository(repo_name)
    if env:
        make_conf_vars = {k: v for k, v in env.items() if not isinstance(v, dict)}
        build_env.write_env(make_conf_vars)
        specialized_envs = {k: v for k, v in env.items() if k not in make_conf_vars}
        for env_name, env in specialized_envs.items():
            build_env.write_env(name=env_name, env_vars=env)
    if repositories:
        for repository in repositories:
            build_env.add_repository(repository.name, repository.sync_type, repository.uri)
    logger.debug('The following repositories are available for the build: ' + ', '.join(build_env.repositories))
    for package, package_config in package_configs.items():
        build_env.write_package_config(package, **package_config)
    if libc:
        packages.append(libc_to_package_name(libc))
    if libc != Libc.musl:
        # This value should depend on the selected profile, but there is currently no musl profile with
        # links to lib directories.
        for prefix in ['', 'usr', 'usr/local']:
            lib_prefix = os.path.join(root_path, prefix)
            lib_path = os.path.join(lib_prefix, 'lib64')
            os.makedirs(lib_path, exist_ok=True)
            os.symlink('lib64', os.path.join(lib_prefix, 'lib'))
    if os.path.exists(os.path.join('/usr', 'portage')):
        _fix_portage_tree_permissions()
    concurrent_jobs = max_concurrent_jobs if max_concurrent_jobs else _max_concurrent_jobs()
    if create_builder:
        _update_builder(max_concurrent_jobs=concurrent_jobs, max_cpu_load=_max_cpu_load())
    _create_rootfs(root_path, *packages, max_concurrent_jobs=concurrent_jobs, max_cpu_load=_max_cpu_load())
    _copy_stdlib(root_path, copy_libstdcpp=stdlib)
    if libc == Libc.glibc:
        with open(os.path.join('/etc', 'locale.gen'), 'a') as locale_conf:
            locale_conf.writelines('{} {}'.format(locale.name, locale.charset))
            subprocess.run('locale-gen')
        _copy_to_rootfs(root_path, '/usr/lib/locale/locale-archive')
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
            _copy_to_rootfs(root_path, f)
