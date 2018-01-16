"""Installs Gentoo portage packages into a specified directory."""

import click
import io
import itertools
import os
import shutil
import subprocess
import tarfile

import docker
import toml


class RootfsError(Exception):
    pass


def _create_rootfs(rootfs_path, *packages, uid=None, gid=None, disable_cache=None):
    print('Creating rootfs at {} containing the following packages:'.format(rootfs_path))
    print(*packages, sep=', ', end=os.linesep, flush=True)
    lib_path = os.path.join(rootfs_path, 'usr', 'lib64')
    os.makedirs(lib_path, exist_ok=True)
    os.symlink('lib64', os.path.join(rootfs_path, 'usr', 'lib'))

    print('Installing build-time dependencies to builder', flush=True)
    if disable_cache:
        arg_prefix = itertools.cycle(['--buildpkg-exclude'])
        disable_cache_args = [arg for tup in zip(arg_prefix, disable_cache) for arg in tup]
    else:
        disable_cache_args = []
    os.environ['FEATURES'] = '-binpkg-logs'
    emerge_bdeps_command = ['emerge', '--verbose', '--onlydeps', '--onlydeps-with-rdeps=n', '--autounmask-continue=y',
                            '--buildpkg', *disable_cache_args, '--usepkg', '--with-bdeps=y', *packages]
    emerge_bdeps_call = subprocess.run(emerge_bdeps_command, stderr=subprocess.PIPE)
    if emerge_bdeps_call.returncode != 0:
        raise RootfsError('Unable to install build-time dependencies.')

    print('Installing runtime dependencies to rootfs', flush=True)
    emerge_rdeps_command = ['emerge', '--verbose', '--root={}'.format(rootfs_path), '--root-deps=rdeps', '--oneshot',
                            '--autounmask-continue=y', '--buildpkg', *disable_cache_args, '--usepkg', *packages]
    emerge_rdeps_call = subprocess.run(emerge_rdeps_command, stderr=subprocess.PIPE)
    if emerge_rdeps_call.returncode != 0:
        raise RootfsError('Unable to install runtime dependencies.')

    # Copy libgcc (e.g. for pthreads)
    for directory_path, subdirs, files in os.walk(os.path.join('/usr', 'lib', 'gcc', 'x86_64-pc-linux-gnu')):
        if 'libgcc_s.so.1' in files:
            shutil.copy(os.path.join(directory_path, 'libgcc_s.so.1'), os.path.join(rootfs_path, 'usr', 'lib'))

    if not uid:
        uid = os.getuid()
    if not gid:
        gid = os.getgid()
    for base_path, dirs, files in os.walk(rootfs_path):
        for d in dirs:
            os.chown(os.path.join(base_path, d), uid, gid)
        for f in files:
            os.chown(os.path.join(base_path, f), uid, gid)


def _create_dockerfile(*cmd: str) -> str:
    command_string = ', '.join(['\"{}\"'.format(c) for c in cmd])
    return """\
    FROM scratch
    COPY rootfs /
    CMD [{}]
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
    if name:
        conf_path = os.path.join('/etc', 'portage', 'env', name)
    else:
        conf_path = os.path.join('/etc', 'portage', 'make.conf')
    with open(conf_path, 'a') as make_conf:
        for line in _dict_to_env_vars(env_vars):
            make_conf.write(line)


def _dict_to_env_vars(d: dict):
    return ('{}="{}"'.format(k, v) for k, v in d.items())


def _write_package_config(package: str, env: list=None):
    if 'env':
        package_config_path = os.path.join('/etc', 'portage', 'package.env')
        with open(package_config_path, 'a') as f:
            package_environments = ' '.join(env)
            f.write('{} {}'.format(package, package_environments))


@click.command(help='Installs the specified packages into to the desired location.')
@click.option('--disable-cache', multiple=True,
                    help='Package that should not be built as a binary package for caching. May occur multiple times.')
@click.option('--libc', help='Libc to be installed into rootfs')
@click.option('--uid', type=int, help='User ID to be set as owner of the rootfs')
@click.option('--gid', type=int, help='Group ID to be set as owner of the rootfs')
def main(disable_cache, libc, uid, gid):
    toml_content = click.get_binary_stream('stdin').read().decode('utf-8')
    config = toml.loads(toml_content)
    rootfs_path = '/tmp/rootfs'
    if 'env' in config:
        make_conf_vars = {k: v for k, v in config['env'].items() if not isinstance(v, dict)}
        _write_env(make_conf_vars)
        specialized_envs = {k: v for k, v in config['env'].items() if k not in make_conf_vars}
        for env_name, env in specialized_envs.items():
            _write_env(name=env_name, env_vars=env)
        config.pop('env')
    package_configs = {k: v for k, v in config.items() if isinstance(v, dict)}
    for package, package_config in package_configs.items():
        _write_package_config(package, **package_config)
    _create_rootfs(rootfs_path, libc, config['package'], uid=uid, gid=gid, disable_cache=disable_cache)
    _docker_image_from_rootfs(rootfs_path, config['tag'], config['command'])


if __name__ == '__main__':
    main()
