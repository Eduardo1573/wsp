#!/usr/bin/env bash
# Rebuild tools/certs/wsp-ca-bundle.pem (certifi roots + the intermediate wsp omits).
set -euo pipefail
cd "$(dirname "$0")/certs"
AIA=$(echo | openssl s_client -connect wsp.kbtu.kz:443 -servername wsp.kbtu.kz 2>/dev/null \
      | openssl x509 -noout -text | grep -oE 'URI:http://crt\.sectigo\.com/[^ ]+\.crt' | cut -d: -f2-)
curl -sfo inter.der "$AIA"
openssl x509 -inform DER -in inter.der -out inter.pem
python3 -c "import certifi,shutil;shutil.copy(certifi.where(),'wsp-ca-bundle.pem')"
cat inter.pem >> wsp-ca-bundle.pem
echo "rebuilt wsp-ca-bundle.pem from $AIA"
