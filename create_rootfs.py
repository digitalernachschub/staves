import os
import shutil
import subprocess


def create_rootfs(rootfs_path, *packages):
    print(f'Creating rootfs at {rootfs_path} containing the following packages:')
    print(*packages, sep=', ', end='', flush=True)
    lib_path = os.path.join(rootfs_path, 'usr', 'lib64')
    os.makedirs(lib_path, exist_ok=True)
    os.symlink('lib64', os.path.join(rootfs_path, 'usr', 'lib'))

    os.environ['FEATURES'] = '-binpkg-logs'
    os.environ['PKGDIR'] = os.path.join('/tmp', 'ameto_ci')
    subprocess.run(['emerge', f'--root={rootfs_path}', '--root-deps=rdeps', '--oneshot', '--buildpkg', '--usepkg', *packages])

    shutil.copyfile(os.path.join('/etc', 'locale.gen'), os.path.join(rootfs_path, 'etc', 'locale.gen'))

    # Copy libgcc (e.g. for pthreads)
    shutil.copy(os.path.join('/usr', 'lib', 'gcc', 'x86_64-pc-linux-gnu', '5.4.0', 'libgcc_s.so.1'), os.path.join(rootfs_path, 'usr', 'lib'))


if __name__ == '__main__':
    import sys
    rootfs_path = sys.argv[1]
    packages = sys.argv[2:]
    create_rootfs(rootfs_path, *packages)
