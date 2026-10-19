#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${1:-$repo_root/caddy-root.crt}"
public_host="${PUBLIC_HOST:-192.168.0.85}"
tls_port="${API_PORT:-18002}"
root_tmp="$(mktemp "${destination}.XXXXXX")"
leaf_tmp="$(mktemp)"
intermediates_tmp="$(mktemp)"
chain_tmp="$(mktemp)"
trap 'rm -f "$root_tmp" "$leaf_tmp" "$intermediates_tmp" "$chain_tmp"' EXIT

docker compose exec -T caddy cat /data/caddy/pki/authorities/local/root.crt > "$root_tmp"
openssl x509 -in "$root_tmp" -noout -text | grep -Eq 'CA:TRUE' || {
  printf 'The exported Caddy certificate is not a CA certificate.\n' >&2
  exit 1
}

openssl s_client \
  -connect "${public_host}:${tls_port}" \
  -servername "$public_host" \
  -showcerts </dev/null > "$chain_tmp" 2>/dev/null
awk -v leaf="$leaf_tmp" -v intermediates="$intermediates_tmp" '
  /-----BEGIN CERTIFICATE-----/ {
    count++
    output = count == 1 ? leaf : intermediates
  }
  output { print > output }
  /-----END CERTIFICATE-----/ {
    close(output)
    output = ""
  }
' "$chain_tmp"
test -s "$leaf_tmp" || {
  printf 'Caddy did not provide a leaf certificate.\n' >&2
  exit 1
}

if [[ "$public_host" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  openssl verify -CAfile "$root_tmp" -untrusted "$intermediates_tmp" \
    -verify_ip "$public_host" "$leaf_tmp"
else
  openssl verify -CAfile "$root_tmp" -untrusted "$intermediates_tmp" \
    -verify_hostname "$public_host" "$leaf_tmp"
fi

printf '\nActive Caddy root certificate:\n'
openssl x509 -in "$root_tmp" -noout -subject -issuer -startdate -enddate -fingerprint -sha256
printf '\nServed leaf certificate:\n'
openssl x509 -in "$leaf_tmp" -noout -subject -issuer -ext subjectAltName
install -m 0644 "$root_tmp" "$destination"
printf '\nInstalled public root certificate at %s\n' "$destination"
