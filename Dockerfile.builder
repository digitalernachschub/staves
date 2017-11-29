FROM gentoo/portage as portage

FROM staves/gentoo-stage3-amd64-musl-hardened

COPY --from=portage /usr/portage /usr/portage

ENV LANG en_US.UTF-8
RUN echo "MAKEOPTS=\"-j$(($(nproc)+1)) -l$(nproc)\"" >> /etc/portage/make.conf && \
  echo 'EMERGE_DEFAULT_OPTS="--nospinner --quiet"' >> /etc/portage/make.conf && \
  echo 'PORTAGE_ELOG_SYSTEM="echo:warn,error"' >> /etc/portage/make.conf && \
  echo 'FEATURES="-news nodoc noinfo noman"' >> /etc/portage/make.conf

# Sandbox uses ptrace which is not permitted by default in Docker
RUN mkdir /etc/portage/env && \
  echo 'FEATURES="-sandbox -usersandbox"' >> /etc/portage/env/no-sandbox && \
  echo "sys-libs/musl no-sandbox" >> /etc/portage/package.env

RUN emerge app-portage/flaggie

RUN flaggie "net-misc/openssh" "-bindist" && \
  flaggie "dev-libs/openssl" "-bindist" && \
  emerge --oneshot --newuse "net-misc/openssh" "dev-libs/openssl" && \
  emerge --update --newuse --deep @world

RUN flaggie "dev-vcs/git" "-gpg" "-perl" "-python" && \
  emerge app-portage/layman && \
  sed --in-place 's/check_official : .*/check_official : No/' /etc/layman/layman.cfg && \
  layman -f && \
  layman -a musl

RUN flaggie "dev-lang/python:3.6" "+~amd64" && \
  emerge dev-lang/python:3.6
COPY create_rootfs.py create_rootfs.py
CMD ["python3.6", "create_rootfs.py"]
