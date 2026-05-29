#!/usr/bin/env bash
# Black-box test of the MyChart microservice.
#
# Drives: GET /health, GET /epic/organizations, POST /epic/auth/start,
# (manual browser auth), POST /epic/auth/finish, then a Patient call to
# Epic's FHIR API with the returned access token.
#
# Usage:
#   ./test_flow.sh                          # uses defaults
#   BASE_URL=http://localhost:8765 ./test_flow.sh
#   ORG_ALIAS=my_chart_central ./test_flow.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
ORG_ALIAS="${ORG_ALIAS:-my_chart_central}"

for tool in curl jq; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Missing required tool: $tool" >&2; exit 1; }
done

bold()   { printf '\033[1m%s\033[0m\n' "$1"; }
step()   { printf '\n\033[1;34m== %s ==\033[0m\n' "$1"; }
warn()   { printf '\033[1;33m%s\033[0m\n' "$1"; }
die()    { printf '\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

mask()   { local s="$1"; [[ ${#s} -le 20 ]] && printf '%s' "$s" || printf '%s…(+%d)' "${s:0:20}" "$((${#s} - 20))"; }

# Parse a form-encoded query string into a value for a given key.
# Reads from the global $qs.
parse_qs_param() {
    local key="$1" pair
    while IFS= read -r pair; do
        if [[ "$pair" == "$key="* ]]; then
            printf '%s' "${pair#*=}"
            return 0
        fi
    done < <(printf '%s\n' "$qs" | tr '&' '\n')
}

bold "Microservice: $BASE_URL"
bold "Organization: $ORG_ALIAS"

step "1. GET /health"
curl --fail-with-body -sS "$BASE_URL/health" | jq .

step "2. GET /epic/organizations"
orgs_json=$(curl --fail-with-body -sS "$BASE_URL/epic/organizations")
echo "$orgs_json" | jq .
fhir_base=$(echo "$orgs_json" | jq -r --arg alias "$ORG_ALIAS" '.[] | select(.alias==$alias) | .endpoint_url')
[[ -n "$fhir_base" && "$fhir_base" != "null" ]] || die "Organization alias '$ORG_ALIAS' not in /epic/organizations"
echo "FHIR base for $ORG_ALIAS: $fhir_base"

step "3. POST /epic/auth/start"
start_req=$(jq -nc --arg alias "$ORG_ALIAS" '{organization_alias:$alias}')
start_resp=$(curl --fail-with-body -sS -X POST \
    -H 'Content-Type: application/json' \
    -d "$start_req" \
    "$BASE_URL/epic/auth/start")
echo "$start_resp" | jq .
authorization_url=$(echo "$start_resp" | jq -r .authorization_url)
state=$(echo "$start_resp" | jq -r .state)
[[ -n "$authorization_url" && "$authorization_url" != "null" ]] || die "No authorization_url in /start response"

step "4. Authorize in browser"
cat <<EOF
Open the URL below in a browser and authenticate with MyChart (e.g. sandbox user
fhircamila / epicepic1). Epic will redirect to the configured redirect_uri with
?code=...&state=... in the URL bar. That page may not load (e.g. no listener on
:3001) — copy the URL from the address bar anyway.

EOF
bold "$authorization_url"
echo

printf 'Paste redirect URL (or just the query string): '
read -r redirect_input
[[ -n "$redirect_input" ]] || die "No input"

qs="${redirect_input#*\?}"       # strip everything up to the first '?'
qs="${qs%%#*}"                   # strip any URL fragment
code=$(parse_qs_param code) || true
returned_state=$(parse_qs_param state) || true

[[ -n "$code" ]] || die "Could not find 'code' parameter in: $redirect_input"
if [[ -n "$returned_state" && "$returned_state" != "$state" ]]; then
    warn "Returned state ($returned_state) does not match issued state ($state)"
fi
echo "Parsed code:  $(mask "$code")"
echo "Parsed state: $returned_state"

step "5. POST /epic/auth/finish"
finish_req=$(jq -nc --arg code "$code" --arg state "${returned_state:-$state}" '{code:$code, state:$state}')
if ! finish_resp=$(curl --fail-with-body -sS -X POST \
        -H 'Content-Type: application/json' \
        -d "$finish_req" \
        "$BASE_URL/epic/auth/finish"); then
    echo "Response body:"
    echo "${finish_resp:-<empty>}" | jq . 2>/dev/null || echo "${finish_resp:-<empty>}"
    die "/epic/auth/finish failed"
fi
# Pretty-print with sensitive fields truncated
echo "$finish_resp" | jq '
    .access_token  = (.access_token  | .[0:20] + "…")
  | .refresh_token = (if .refresh_token then (.refresh_token | .[0:20] + "…") else null end)
  | .id_token      = (if .id_token      then (.id_token      | .[0:20] + "…") else null end)
'

access_token=$(echo "$finish_resp" | jq -r .access_token)
patient_id=$(echo "$finish_resp" | jq -r .patient)
[[ -n "$access_token" && "$access_token" != "null" ]] || die "No access_token in /finish response"

step "6. GET $fhir_base/Patient (verify token works)"
patient_search=$(curl --fail-with-body -sS \
    -H "Authorization: Bearer $access_token" \
    -H 'Accept: application/fhir+json' \
    "$fhir_base/Patient")
echo "$patient_search" | jq '{
    resourceType,
    type,
    total,
    entry_count: (.entry // [] | length),
    first_entry: ((.entry // [])[0].resource | {resourceType, id, name})
}'

if [[ -n "$patient_id" && "$patient_id" != "null" ]]; then
    step "7. GET $fhir_base/Patient/$patient_id (SMART launch context)"
    curl --fail-with-body -sS \
        -H "Authorization: Bearer $access_token" \
        -H 'Accept: application/fhir+json' \
        "$fhir_base/Patient/$patient_id" \
        | jq '{resourceType, id, name, birthDate, gender}'
fi

echo
bold "Done."
