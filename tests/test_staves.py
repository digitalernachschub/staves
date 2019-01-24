import os

import toml
from click.testing import CliRunner
from staves.cli import main


def test_creates_lib_symlink(tmpdir, monkeypatch, mocker):
    unprivileged_test_root = tmpdir.join('test_root')
    monkeypatch.setenv('ROOT', unprivileged_test_root)
    rootfs_path = tmpdir.join('rootfs')
    config = toml.dumps(dict(
        name='staves_test',
        packages=['virtual/libintl'],
        command=''
    ))
    mocker.patch('staves.builders.gentoo._fix_portage_tree_permissions')
    mocker.patch('staves.builders.gentoo._update_builder')
    mocker.patch('staves.builders.gentoo._create_rootfs')
    cli = CliRunner()

    cli.invoke(main, input=config, args=['--rootfs_path', rootfs_path, '--packaging', 'none', 'latest'])

    assert os.path.islink(os.path.join(rootfs_path, 'lib'))
    assert os.path.islink(os.path.join(rootfs_path, 'usr', 'lib'))
    assert os.path.islink(os.path.join(rootfs_path, 'usr', 'local', 'lib'))


def test_copies_libgcc(tmpdir, monkeypatch, mocker):
    unprivileged_test_root = tmpdir.join('test_root')
    monkeypatch.setenv('ROOT', unprivileged_test_root)
    rootfs_path = tmpdir.join('rootfs')
    config = toml.dumps(dict(
        name='staves_test',
        packages=['virtual/libintl'],
        command=''
    ))
    mocker.patch('staves.builders.gentoo._fix_portage_tree_permissions')
    mocker.patch('staves.builders.gentoo._update_builder')
    mocker.patch('staves.builders.gentoo._create_rootfs')
    cli = CliRunner()

    cli.invoke(main, input=config, args=['--rootfs_path', rootfs_path, '--packaging', 'none', 'latest'])

    assert os.path.exists(os.path.join(rootfs_path, 'usr', 'lib64', 'libgcc_s.so.1'))
