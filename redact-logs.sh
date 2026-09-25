#!/bin/sh
# Streaming filter for application diagnostics, before the container log collector.
# Drop URL query values and long token-like strings. Keep short human-readable diagnostics.
exec awk '
{
  line=$0
  gsub(/\?[^ \t"<>]*/, "?[REDACTED]", line)
  out=""
  while (match(line, /[-A-Za-z0-9_.\/:+=@%]+/)) {
    out=out substr(line,1,RSTART-1)
    token=substr(line,RSTART,RLENGTH)
    out=out (length(token)>=24 ? "[REDACTED]" : token)
    line=substr(line,RSTART+RLENGTH)
  }
  print out line
  fflush()
}'
