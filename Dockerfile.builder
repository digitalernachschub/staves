FROM gentoo/portage as portage

FROM staves/gentoo-stage3-amd64-musl-hardened

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

RUN flaggie "net-misc/openssh" "-bindist"
RUN flaggie "dev-libs/openssl" "-bindist"
RUN emerge --oneshot --newuse "net-misc/openssh" "dev-libs/openssl"
RUN emerge --newuse @world --exclude gcc

RUN flaggie "dev-vcs/git" "-gpg" "-perl" "-python"
RUN emerge app-portage/layman
RUN sed --in-place 's/check_official : .*/check_official : No/' /etc/layman/layman.cfg
COPY overlays /etc/layman/overlays
RUN layman -f
RUN layman -a musl
RUN layman -a ameto

RUN flaggie "dev-lang/python:3.6" "+~amd64"
RUN emerge dev-lang/python:3.6
COPY create_rootfs.py create_rootfs.py
CMD ["python3.6", "create_rootfs.py"]