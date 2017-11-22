FROM gentoo/portage as portage

FROM ameto/gentoo-stage3-amd64-musl-hardened

COPY --from=portage /usr/portage /usr/portage

ENV LANG en_US.UTF-8
RUN echo "MAKEOPTS=\"-j$(($(nproc)+1)) -l$(nproc)\"" >> /etc/portage/make.conf
RUN echo 'EMERGE_DEFAULT_OPTS="--quiet"' >> /etc/portage/make.conf

RUN emerge app-portage/flaggie

# We do not need openssh and it requires dev-libs/openssl[bindist], unless we also re-compile openssh with USE="-bindist"
RUN emerge -C net-misc/openssh
RUN flaggie "dev-libs/openssl" "-bindist"
RUN emerge -1N openssl

RUN flaggie "dev-vcs/git" "-gpg -perl"
RUN emerge app-portage/layman
RUN layman -f
RUN layman -a musl

RUN echo 'PYTHON_TARGETS="python3_6"' >> /etc/portage/make.conf
RUN flaggie "dev-lang/python:3.6" "+~amd64"
RUN emerge dev-lang/python:3.6
RUN emerge -N @world --exclude gcc
RUN eselect python set --python3 python3.6
COPY create_rootfs.py create_rootfs.py
CMD ["python3.6", "create_rootfs.py"]