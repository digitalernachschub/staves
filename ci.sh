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
    local build_date="$1"
    stage3_filename=stage3-amd64-musl-hardened-${build_date}.tar.bz2
    stage3_path=/tmp/${stage3_filename}
    if [ ! -f ${stage3_path} ]; then
        wget -O ${stage3_path} http://distfiles.gentoo.org/experimental/amd64/musl/${stage3_filename}
    fi
    mkdir gentoo
    fakeroot tar xpjf ${stage3_path} -C gentoo
    docker build --tag staves/gentoo-stage3-amd64-musl-hardened:${build_date} --tag staves/gentoo-stage3-amd64-musl-hardened:latest -f Dockerfile.stage3 .
}

project_name=$(basename $(pwd))
version=$(git describe --tags --always --dirty)
version=${version#${project_name}-}
setup_test_env
run_unit_tests

musl_stage3_date="20180304"
create_stage3_image ${musl_stage3_date}
docker build --tag "staves/bootstrap-x86_64-musl:${version}.${musl_stage3_date}" --no-cache -f Dockerfile.x86_64-musl .
cat x86_64-musl.toml | docker run --rm --interactive \
    --mount type=volume,source=staves-x86_64-musl-cache,target=/usr/portage/packages \
    --mount type=bind,source=/run/docker.sock,target=/run/docker.sock \
    "staves/bootstrap-x86_64-musl:${version}.${musl_stage3_date}" --libc "sys-libs/musl" "${version}.${musl_stage3_date}"
if [[ $(git tag --list ${project_name}-${version}) ]]; then
  docker tag "staves/x86_64-musl:${version}.${musl_stage3_date}" "staves/x86_64-musl:${version}"
  docker tag "staves/x86_64-musl:${version}.${musl_stage3_date}" "staves/x86_64-musl:${version%.*}"
  docker tag "staves/x86_64-musl:${version}.${musl_stage3_date}" "staves/x86_64-musl:${version%%.*}"
fi

glibc_stage3_date="20180228"
docker build --tag "staves/bootstrap-x86_64-glibc:${version}.${glibc_stage3_date}" --no-cache -f Dockerfile.x86_64-glibc .
cat x86_64-glibc.toml | docker run --rm --interactive \
    --mount type=volume,source=staves-x86_64-glibc-cache,target=/usr/portage/packages \
    --mount type=bind,source=/run/docker.sock,target=/run/docker.sock \
    "staves/bootstrap-x86_64-glibc:${version}.${glibc_stage3_date}" --libc "sys-libs/glibc" "${version}.${glibc_stage3_date}"
if [[ $(git tag --list ${project_name}-${version}) ]]; then
  docker tag "staves/x86_64-glibc:${version}.${glibc_stage3_date}" "staves/x86_64-glibc:${version}"
  docker tag "staves/x86_64-glibc:${version}.${glibc_stage3_date}" "staves/x86_64-glibc:${version%.*}"
  docker tag "staves/x86_64-glibc:${version}.${glibc_stage3_date}" "staves/x86_64-glibc:${version%%.*}"
fi
