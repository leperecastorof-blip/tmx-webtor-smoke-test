FROM ghcr.io/webtor-io/self-hosted@sha256:6d6062a4c941ccd9649c38927c791390539f6f287571195370e8e1c4ad1cbda2
# The only root-level links are constructed INSIDE the Docker build filesystem.
# Never package a host-side link-creation script.
RUN mkdir -p /var/lib/webtor /etc/tmx-webtor && printf '%s\n' 'tmx-webtor-ephemeral-test-v1' > /etc/tmx-webtor/image-sentinel && \
    for name in data pgdata storage; do \
      if [ -e "/$name" ] || [ -L "/$name" ]; then \
        test -d "/$name" && test ! -L "/$name" && rmdir "/$name" || exit 78; \
      fi; \
      ln -s "/var/lib/webtor/$name" "/$name" || exit 78; \
    done
COPY entrypoint.sh /usr/local/bin/tmx-webtor-entrypoint
RUN chmod 0555 /usr/local/bin/tmx-webtor-entrypoint
ENV TMX_STORAGE_MODE=ephemeral-test
LABEL tmx.purpose="ephemeral-validation-only"
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=6s --start-period=120s --retries=3 CMD curl --fail --silent --max-time 5 --output /dev/null http://127.0.0.1:8080/login || exit 1
ENTRYPOINT ["/usr/local/bin/tmx-webtor-entrypoint"]
