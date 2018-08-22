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

portage_snapshot="20180821"
musl_stage3_date="20180804"
create_stage3_image ${musl_stage3_date}
full_version="${version}.${musl_stage3_date}"
docker build --tag "staves/bootstrap-x86_64-musl:${full_version}" --no-cache \
    -f Dockerfile.x86_64-musl --build-arg STAGE3=${musl_stage3_date} --build-arg PORTAGE_SNAPSHOT=${portage_snapshot} .
cat x86_64-musl.toml | docker run --rm --interactive \
    --mount type=volume,source=staves-x86_64-musl-cache,target=/usr/portage/packages \
    --mount type=bind,source=/run/docker.sock,target=/run/docker.sock \
    "staves/bootstrap-x86_64-musl:${full_version}" --create-builder --libc "sys-libs/musl" "${full_version}"
if [[ $(git tag --list ${project_name}-${version}) ]]; then
  docker tag "staves/x86_64-musl:${full_version}" "staves/x86_64-musl:${version}"
  docker tag "staves/x86_64-musl:${full_version}" "staves/x86_64-musl:${version%.*}"
  docker tag "staves/x86_64-musl:${full_version}" "staves/x86_64-musl:${version%%.*}"
fi

glibc_stage3_date="20180821"
full_version="${version}.${glibc_stage3_date}"
docker build --tag "staves/bootstrap-x86_64-glibc:${full_version}" --no-cache \
    -f Dockerfile.x86_64-glibc --build-arg STAGE3=${glibc_stage3_date} --build-arg PORTAGE_SNAPSHOT=${portage_snapshot} .
cat x86_64-glibc.toml | docker run --rm --interactive \
    --mount type=volume,source=staves-x86_64-glibc-cache,target=/usr/portage/packages \
    --mount type=bind,source=/run/docker.sock,target=/run/docker.sock \
    "staves/bootstrap-x86_64-glibc:${full_version}" --create-builder --libc "sys-libs/glibc" "${full_version}"
if [[ $(git tag --list ${project_name}-${version}) ]]; then
  docker tag "staves/x86_64-glibc:${full_version}" "staves/x86_64-glibc:${version}"
  docker tag "staves/x86_64-glibc:${full_version}" "staves/x86_64-glibc:${version%.*}"
  docker tag "staves/x86_64-glibc:${full_version}" "staves/x86_64-glibc:${version%%.*}"
fi
