#!/usr/bin/env bash
set -e

setup_test_env() {
    echo "Setting up test environment…"
    python3.6 -m venv venv
    . venv/bin/activate
    pip install pip-tools
    pip-sync requirements.txt dev-requirements.txt
}

run_unit_tests() {
    PYTHONPATH=. pytest
}

create_stage3_image() {
    build_date="20171204"
    stage3_filename=stage3-amd64-musl-hardened-${build_date}.tar.bz2
    stage3_path=/tmp/${stage3_filename}
    if [ ! -f ${stage3_path} ]; then
        wget -O ${stage3_path} http://distfiles.gentoo.org/experimental/amd64/musl/${stage3_filename}
    fi
    mkdir gentoo
    fakeroot tar xpjf ${stage3_path} -C gentoo
    docker build --tag staves/gentoo-stage3-amd64-musl-hardened:${build_date} --tag staves/gentoo-stage3-amd64-musl-hardened:latest -f Dockerfile.stage3 .
}

setup_test_env
run_unit_tests

create_stage3_image
docker build --tag staves/builder-musl -f Dockerfile.builder-musl .
docker build --tag staves/builder-glibc -f Dockerfile.builder-glibc .
