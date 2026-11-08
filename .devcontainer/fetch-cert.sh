#!/bin/bash

# How to use this script:
#   - Save the code into a file named: fetch-cert.sh.
#   - Make it executable: chmod +x fetch-cert.sh
#   - Run it: ./fetch-cert.sh
#   - Certificates are in 'certs/' directory

# Add the URLs for all the certificates needed
CERT_DIR="certs"
URLS=(
  "http://ca.example.com/examplePKICertChain-Enterprise-NA.zip"
  "http://ca.example.com/examplePKICertChain-Resource-NA.zip"
)

# Check if unzip is present (not install by default on Debian/Ubuntu)
if ! command -v unzip &> /dev/null; then
  echo "[ERROR] 'unzip' is required but not installed. Aborting." >&2
  exit 1
fi

# Create the target directory if it doesn't exist
mkdir -p ${CERT_DIR}

echo "Downloading example PKI certificate chains..."

# -f : Fails on HTTP errors (like 404) so it doesn't download an HTML error page into our ZIP file
# -S : Prints curl's native error message to the console if it fails
for URL in "${URLS[@]}"; do
  # Automatically extract the filename from the end of the URL (e.g., examplePKICertChain-Enterprise-NA.zip)
  FILENAME=$(basename "$URL")
  
  if ! curl -sSLf -o "$FILENAME" "$URL"; then
    echo -e "[\033[31mERROR\033[0m] Failed to download $FILENAME. Skipping..."
  else
    unzip -o -q "$FILENAME" -d "${CERT_DIR}/"
    rm "$FILENAME"
  fi
done

echo "Fixing Windows line endings..."
# Suppress error if no .crt files are found
sed -i 's/\r$//' ${CERT_DIR}/*.crt 2>/dev/null || true

echo "----------------------------------------"
echo "Checking certificates for expiration..."
echo "----------------------------------------"

# Enable nullglob in case the directory is empty or lacks .crt files
shopt -s nullglob
for cert in ${CERT_DIR}/*.crt; do
  # -checkend 0 checks if the certificate expires in the next 0 seconds.
  if openssl x509 -checkend 0 -noout -in "$cert" >/dev/null 2>&1; then
    echo -e "[\033[32mVALID\033[0m]   $(basename "$cert")"
  else
    echo -e "[\033[31mEXPIRED\033[0m] $(basename "$cert")"
    EXP_DATE=$(openssl x509 -enddate -noout -in "$cert" | cut -d= -f2)
    echo "          -> Expired on: $EXP_DATE"
  fi
done
shopt -u nullglob

echo "----------------------------------------"
echo "Done."
