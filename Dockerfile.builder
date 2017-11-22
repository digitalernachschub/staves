FROM gentoo/portage as portage

FROM ameto/gentoo-stage3-amd64-musl-hardened

COPY --from=portage /usr/portage /usr/portage

ENV LANG en_US.UTF-8
RUN echo "MAKEOPTS=\"-j$(($(nproc)+1)) -l$(nproc)\"" >> /etc/portage/make.conf
RUN echo 'EMERGE_DEFAULT_OPTS="--nospinner --quiet"' >> /etc/portage/make.conf
RUN echo 'PORTAGE_ELOG_SYSTEM="echo:warn,error"' >> /etc/portage/make.conf
RUN echo 'FEATURES="-news nodoc noinfo noman"' >> /etc/portage/make.conf

# Sandbox uses ptrace which is not permitted by default in Docker
RUN mkdir /etc/portage/env
RUN echo 'FEATURES="-sandbox -usersandbox"' >> /etc/portage/env/no-sandbox
RUN echo "sys-libs/musl no-sandbox" >> /etc/portage/package.env

RUN emerge app-portage/flaggie

# We do not need openssh and it requires dev-libs/openssl[bindist], unless we also re-compile openssh with USE="-bindist"
RUN emerge --rage-clean net-misc/openssh
RUN flaggie "dev-libs/openssl" "-bindist"
RUN emerge -1N openssl

RUN flaggie "dev-vcs/git" "-curl" "-gpg" "-perl" "-webdav"
RUN emerge app-portage/layman
RUN layman -f
RUN layman -a musl

RUN flaggie "dev-lang/python:3.6" "+~amd64"
RUN emerge dev-lang/python:3.6
RUN emerge -N @world --exclude gcc
COPY create_rootfs.py create_rootfs.py
CMD ["python3.6", "create_rootfs.py"]