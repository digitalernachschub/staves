import os

from staves import _create_rootfs


def test_creates_lib_symlink(tmpdir, monkeypatch):
    package_dir = tmpdir.join('packages')
    monkeypatch.setenv('PKGDIR', package_dir)
    unprivileged_test_root = tmpdir.join('test_root')
    monkeypatch.setenv('ROOT', unprivileged_test_root)
    rootfs_path = tmpdir.join('rootfs')
    _create_rootfs(rootfs_path, 'virtual/libintl')

    assert os.path.islink(os.path.join(rootfs_path, 'lib'))
    assert os.path.islink(os.path.join(rootfs_path, 'usr', 'lib'))
    assert os.path.islink(os.path.join(rootfs_path, 'usr', 'local', 'lib'))


def test_copies_libgcc(tmpdir, monkeypatch):
    package_dir = tmpdir.join('packages')
    monkeypatch.setenv('PKGDIR', package_dir)
    unprivileged_test_root = tmpdir.join('test_root')
    monkeypatch.setenv('ROOT', unprivileged_test_root)
    rootfs_path = tmpdir.join('rootfs')
    _create_rootfs(rootfs_path, 'virtual/libintl')

    assert os.path.exists(os.path.join(rootfs_path, 'usr', 'lib64', 'libgcc_s.so.1'))


def test_sets_uid_and_gid(tmpdir, monkeypatch, mocker):
    package_dir = tmpdir.join('packages')
    monkeypatch.setenv('PKGDIR', package_dir)
    unprivileged_test_root = tmpdir.join('test_root')
    monkeypatch.setenv('ROOT', unprivileged_test_root)
    rootfs_path = tmpdir.join('rootfs')
    uid = 42
    gid = 43
    mocker.patch('os.chown')
    _create_rootfs(rootfs_path, 'virtual/libintl', uid=uid, gid=gid)

    for base_path, dirs, files in os.walk(rootfs_path):
        for d in dirs:
            os.chown.assert_any_call(os.path.join(base_path, d), uid, gid)
        for f in files:
            os.chown.assert_any_call(os.path.join(base_path, f), uid, gid)
