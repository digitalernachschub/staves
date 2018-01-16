"""Installs Gentoo portage packages into a specified directory."""

import argparse
import io
import os
import shutil
import subprocess
import tarfile

import docker


class RootfsError(Exception):
    pass


def create_rootfs(rootfs_path, *packages, uid=None, gid=None):
    print('Creating rootfs at {} containing the following packages:'.format(rootfs_path))
    print(*packages, sep=', ', end='', flush=True)
    lib_path = os.path.join(rootfs_path, 'usr', 'lib64')
    os.makedirs(lib_path, exist_ok=True)
    os.symlink('lib64', os.path.join(rootfs_path, 'usr', 'lib'))

    print('Installing build-time dependencies to builder', flush=True)
    os.environ['FEATURES'] = '-binpkg-logs'
    emerge_bdeps_command = ['emerge', '--verbose', '--onlydeps', '--onlydeps-with-rdeps=n', '--autounmask-continue=y',
                            '--buildpkg', '--usepkg', '--with-bdeps=y', *packages]
    emerge_bdeps_call = subprocess.run(emerge_bdeps_command, stderr=subprocess.PIPE)
    if emerge_bdeps_call.returncode != 0:
        raise RootfsError('Unable to install build-time dependencies.')

    print('Installing runtime dependencies to rootfs', flush=True)
    emerge_rdeps_command = ['emerge', '--verbose', '--root={}'.format(rootfs_path), '--root-deps=rdeps', '--oneshot',
                            '--autounmask-continue=y', '--buildpkg', '--usepkg', *packages]
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


def _create_dockerfile(cmd: str) -> str:
    return """\
    FROM scratch
    COPY rootfs /
    CMD ["{}"]
    """.format(cmd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Installs the specified packages into to the desired location.')
    parser.add_argument('command', help='Start command to be used for the container')
    parser.add_argument('tag', help='Image tag')
    parser.add_argument('package', help='Package to install')
    parser.add_argument('--libc', help='Libc to be installed into rootfs')
    parser.add_argument('--uid', type=int, help='User ID to be set as owner of the rootfs')
    parser.add_argument('--gid', type=int, help='Group ID to be set as owner of the rootfs')
    args = parser.parse_args()
    rootfs_path = '/tmp/rootfs'
    create_rootfs(rootfs_path, args.libc, args.package, uid=args.uid, gid=args.gid)
    client = docker.from_env()
    dockerfile = _create_dockerfile(args.command).encode('utf-8')
    context = io.BytesIO()
    rootfs_basepath = os.path.dirname(rootfs_path)
    with tarfile.open(fileobj=context, mode='w') as tar:
        dockerfile_info = tarfile.TarInfo(name="Dockerfile")
        dockerfile_info.size = len(dockerfile)
        tar.addfile(dockerfile_info, fileobj=io.BytesIO(dockerfile))
        tar.add(name=rootfs_path, arcname='rootfs')
    context.seek(0)
    client.images.build(fileobj=context, tag=args.tag, custom_context=True)
