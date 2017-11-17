import os

from create_rootfs import create_rootfs


def test_creates_lib_symlink(tmpdir):
    rootfs_path = tmpdir.join('rootfs')
    create_rootfs(rootfs_path, 'virtual/libintl')

    assert os.path.islink(os.path.join(rootfs_path, 'usr', 'lib'))


def test_copies_libgcc(tmpdir):
    rootfs_path = tmpdir.join('rootfs')
    create_rootfs(rootfs_path, 'virtual/libintl')

    assert os.path.exists(os.path.join(rootfs_path, 'usr', 'lib64', 'libgcc_s.so.1'))


def test_creates_locale_gen(tmpdir):
    rootfs_path = tmpdir.join('rootfs')
    create_rootfs(rootfs_path, 'virtual/libintl')

    assert os.path.exists(os.path.join(rootfs_path, 'etc', 'locale.gen'))
