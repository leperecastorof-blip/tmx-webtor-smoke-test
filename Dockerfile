FROM ghcr.io/webtor-io/self-hosted@sha256:6d6062a4c941ccd9649c38927c791390539f6f287571195370e8e1c4ad1cbda2
# The only root-level links are constructed INSIDE the Docker build filesystem.
# Never package a host-side link-creation script.
RUN mkdir -p /var/lib/webtor /etc/tmx-webtor && printf '%s\n' 'tmx-webtor-confined-v2' > /etc/tmx-webtor/image-sentinel && \
    for name in data pgdata storage; do \
      if [ -e "/$name" ] || [ -L "/$name" ]; then \
        test -d "/$name" && test ! -L "/$name" && rmdir "/$name" || exit 78; \
      fi; \
      ln -s "/var/lib/webtor/$name" "/$name" || exit 78; \
    done
COPY entrypoint.sh /usr/local/bin/tmx-webtor-entrypoint
RUN chmod 0555 /usr/local/bin/tmx-webtor-entrypoint
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=6s --start-period=120s --retries=3 CMD curl --fail --silent --max-time 5 --output /dev/null http://127.0.0.1:8080/login || exit 1
ENTRYPOINT ["/usr/local/bin/tmx-webtor-entrypoint"]

# s6 and nginx runtime artifacts are confined to declared /run tmpfs and config volume.
RUN sed -i '1i pid /run/nginx/nginx.pid;' /usr/local/nginx/conf/nginx.template.conf && \
    sed -i '/^http {/a\    client_body_temp_path /run/nginx/client_body;\n    proxy_temp_path /run/nginx/proxy;\n    fastcgi_temp_path /run/nginx/fastcgi;\n    uwsgi_temp_path /run/nginx/uwsgi;\n    scgi_temp_path /run/nginx/scgi;' /usr/local/nginx/conf/nginx.template.conf

# Filter app diagnostics before s6-log writes to Docker stdout/stderr.
COPY redact-logs.sh /usr/local/bin/tmx-redact-logs
RUN chmod 0555 /usr/local/bin/tmx-redact-logs && \
    find /etc/s6-overlay/s6-rc.d -type f -name run -exec sed -i 's/| s6-log/| \/usr\/local\/bin\/tmx-redact-logs | s6-log/g' {} \; && \
    grep -q 'tmx-redact-logs' /etc/s6-overlay/s6-rc.d/rest-api/run
