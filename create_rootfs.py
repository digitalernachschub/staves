"""Installs Gentoo portage packages into a specified directory."""

import os
import shutil
import subprocess


def create_rootfs(rootfs_path, *packages, uid=None, gid=None):
    print(f'Creating rootfs at {rootfs_path} containing the following packages:')
    print(*packages, sep=', ', end='', flush=True)
    lib_path = os.path.join(rootfs_path, 'usr', 'lib64')
    os.makedirs(lib_path, exist_ok=True)
    os.symlink('lib64', os.path.join(rootfs_path, 'usr', 'lib'))

    os.environ['FEATURES'] = '-binpkg-logs'
    emerge_bdeps_call = subprocess.run(['emerge', '--verbose', '--onlydeps', '--onlydeps-with-rdeps=n', '--buildpkg', '--usepkg', *packages], stderr=subprocess.PIPE)
    if emerge_bdeps_call.returncode != 0:
        print(emerge_bdeps_call.stderr)
        return
    emerge_call = subprocess.run(['emerge', '--verbose', f'--root={rootfs_path}', '--root-deps=rdeps', '--oneshot', '--buildpkg', '--usepkg', *packages], stderr=subprocess.PIPE)
    if emerge_call.returncode != 0:
        print(emerge_call.stderr)
        return

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
    import sys
    rootfs_path = sys.argv[1]
    packages = sys.argv[2:]
    create_rootfs(rootfs_path, *packages)
