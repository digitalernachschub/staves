"""Installs Gentoo portage packages into a specified directory."""

import argparse
import os
import shutil
import subprocess


class RootfsError(Exception):
    pass


def create_rootfs(rootfs_path, *packages, uid=None, gid=None):
    print('Creating rootfs at {} containing the following packages:'.format(rootfs_path))
    print(*packages, sep=', ', end='', flush=True)
    lib_path = os.path.join(rootfs_path, 'usr', 'lib64')
    os.makedirs(lib_path, exist_ok=True)
    os.symlink('lib64', os.path.join(rootfs_path, 'usr', 'lib'))

    print('Installing build-time dependencies to builder')
    os.environ['FEATURES'] = '-binpkg-logs'
    emerge_bdeps_command = ['emerge', '--verbose', '--onlydeps', '--onlydeps-with-rdeps=n', '--autounmask-continue=y',
                            '--buildpkg', '--usepkg', '--with-bdeps=y', *packages]
    subprocess.run(emerge_bdeps_command + ['--pretend'])
    emerge_bdeps_call = subprocess.run(emerge_bdeps_command, stderr=subprocess.PIPE)
    if emerge_bdeps_call.returncode != 0:
        raise RootfsError('Unable to install build-time dependencies.')
    print('Installing runtime dependencies to rootfs')
    emerge_rdeps_command = ['emerge', '--verbose', '--root={}'.format(rootfs_path), '--root-deps=rdeps', '--oneshot',
                            '--autounmask-continue=y', '--buildpkg', '--usepkg', *packages]
    subprocess.run(emerge_rdeps_command + ['--pretend'])
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Installs the specified packages into to the desired location.')
    parser.add_argument('rootfs_path', help='Path to install the packages to')
    parser.add_argument('packages', metavar='package', nargs='+', help='Package to install')
    parser.add_argument('--uid', type=int, help='User ID to be set as owner of the rootfs')
    parser.add_argument('--gid', type=int, help='Group ID to be set as owner of the rootfs')
    args = parser.parse_args()
    create_rootfs(args.rootfs_path, *args.packages, uid=args.uid, gid=args.gid)
