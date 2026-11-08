#!/bin/zsh

# ==============================================================================
# Install company-approved CA certificates in Debian's system trust store and
# Python's certifi bundle. This is needed when a corporate proxy inspects TLS
# connections or internal services use a private CA.
#
# Certificate archives must be reachable from inside the dev container. Obtain
# their URLs from an approved company source. Downloads over HTTP are not
# authenticated or protected in transit.
#
# This script reports problems but exits successfully so certificate setup
# does not block container creation. It is safe to rerun manually, for example
# after a download failure: zsh .devcontainer/get-certs.sh
#
# Debian CA trust store: /etc/ssl/certs/ca-certificates.crt
# Python CA trust store: $(python3 -m certifi)
#
# Make it executable:
#   chmod +x .devcontainer/get-certs.sh
# Add this line in: .devcontainer/devcontainer.json
#   "onCreateCommand": "zsh .devcontainer/get-certs.sh",
#
# ==============================================================================

# List company-approved certificate archives reachable from this container.
# Every valid, unexpired .crt file in each archive is installed.
URLS=(
  # This endpoint uses HTTP; use it only if its source and network path are trusted.
  "http://cdp.example.com/examplePKICertChain-Enterprise.zip"
)

DEBIAN_CA_DIR="/usr/local/share/ca-certificates"
FAILED=0

info()  { echo -e "[\033[32m$1\033[0m] $2"; }
error() { echo -e "[\033[31m$1\033[0m] $2"; FAILED=$((FAILED + 1)); }

# Print the final status and leave without ever failing the dev container
finish() {
  if [ "$FAILED" -eq 0 ]; then
    echo -e "\n\033[1;42m\033[1;37m ============================================================ \033[0m"
    echo -e "\033[1;32m ✅  CERTIFICATES INSTALLED.                                  \033[0m"
    echo -e "\033[1;42m\033[1;37m ============================================================ \033[0m\n"
  else
    echo -e "\n\033[1;41m\033[1;37m ============================================================ \033[0m"
    echo -e "\033[1;33m ⚠️  CERTIFICATES: $FAILED problem(s), see the messages above.  \033[0m"
    echo -e "\033[1;33m    TLS to private servers may fail. To try again, run:       \033[0m"
    echo -e "\033[1;33m    zsh .devcontainer/get-certs.sh                            \033[0m"
    echo -e "\033[1;41m\033[1;37m ============================================================ \033[0m\n"
  fi
  exit 0
}

# Check that the required download, archive, certificate, and privilege tools are installed.
for TOOL in curl unzip openssl sudo; do
  if ! command -v "$TOOL" &> /dev/null; then
    error "ERROR" "'$TOOL' is required but not installed."
    finish
  fi
done

# Use a temporary directory outside the workspace and remove it on exit.
CERT_DIR=$(mktemp -d) || { error "ERROR" "Could not create a temporary directory."; finish; }
trap 'rm -rf "$CERT_DIR"' EXIT

echo "Downloading PKI certificate chains..."

# -f: Treat HTTP errors (such as 404) as failures instead of saving an error page as a ZIP.
# -S: Show curl's error message when a request fails.
# --connect-timeout/--max-time: Bound how long an unreachable server can delay startup.
for URL in "${URLS[@]}"; do
  # Use the final URL component as the downloaded archive's filename.
  FILENAME=$(basename "$URL")

  if ! curl -sSLf --connect-timeout 10 --max-time 60 -o "${CERT_DIR}/${FILENAME}" "$URL"; then
    error "ERROR" "Failed to download $FILENAME. Skipping..."
  # -j: Ignore paths inside the archive and extract its files directly into the temporary directory.
  elif ! unzip -o -q -j "${CERT_DIR}/${FILENAME}" -d "${CERT_DIR}/"; then
    error "ERROR" "Failed to extract $FILENAME. Skipping..."
  fi
done

echo "----------------------------------------"
echo "Checking certificates..."
echo "----------------------------------------"

# Keep only parseable, unexpired certificates.
# (N) makes an unmatched glob expand to an empty list instead of raising a zsh error.
VALID_CERTS=()
for cert in ${CERT_DIR}/*.crt(N); do
  NAME=$(basename "$cert")

  # Remove CR characters, then let OpenSSL validate and write canonical PEM with a final newline.
  if ! tr -d '\r' < "$cert" > "${cert}.normalized" ||
    ! openssl x509 -in "${cert}.normalized" -out "${cert}.pem" 2>/dev/null; then
    error "INVALID" "$NAME is not a certificate. Skipping..."
  # -checkend 0 rejects certificates that have already expired.
  elif ! openssl x509 -checkend 0 -noout -in "${cert}.pem" >/dev/null 2>&1; then
    error "EXPIRED" "$NAME expired on $(openssl x509 -enddate -noout -in "${cert}.pem" | cut -d= -f2). Skipping..."
  else
    info "VALID" "$NAME"
    VALID_CERTS+=("$cert")
  fi
done

if [ ${#VALID_CERTS} -eq 0 ]; then
  error "ERROR" "No valid certificate to install."
  finish
fi

echo "----------------------------------------"
echo "Installing in the Debian trust store..."
echo "----------------------------------------"

# -n: Fail immediately rather than prompting for a sudo password during setup.
DEBIAN_READY=1
for cert in "${VALID_CERTS[@]}"; do
  if ! sudo -n install -m 0644 "${cert}.pem" "${DEBIAN_CA_DIR}/$(basename "$cert")"; then
    error "ERROR" "Failed to copy $(basename "$cert") to $DEBIAN_CA_DIR."
    DEBIAN_READY=0
  fi
done

if ! OUTPUT=$(sudo -n update-ca-certificates 2>&1); then
  echo "$OUTPUT"
  error "ERROR" "update-ca-certificates failed."
elif [ "$DEBIAN_READY" -eq 1 ]; then
  info "OK" "Debian trust store is up to date."
fi

echo "----------------------------------------"
echo "Installing in the Python trust store..."
echo "----------------------------------------"

if ! CERTIFI_PEM=$(python3 -m certifi 2>/dev/null) || [ ! -f "$CERTIFI_PEM" ]; then
  error "ERROR" "Could not find the certifi bundle."
  finish
fi

# Mark each appended certificate by its SHA-256 fingerprint so rerunning the
# script does not add the same certificate to the certifi bundle again.
for cert in "${VALID_CERTS[@]}"; do
  NAME=$(basename "$cert")
  MARKER="# get-certs.sh $(openssl x509 -fingerprint -sha256 -noout -in "${cert}.pem")"

  if grep -qxF "$MARKER" "$CERTIFI_PEM"; then
    info "OK" "$NAME is already in certifi."
  elif { printf '\n%s\n' "$MARKER"; cat "${cert}.pem"; } 2>/dev/null >> "$CERTIFI_PEM"; then
    info "OK" "$NAME added to certifi."
  else
    error "ERROR" "Failed to add $NAME to $CERTIFI_PEM."
  fi
done

finish
