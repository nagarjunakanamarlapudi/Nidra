#!/bin/sh
set -e

# Map day name → busybox crond DOW number (sun=0, mon=1, … sat=6)
day_to_dow() {
    case "$1" in
        sun) echo 0 ;;
        mon) echo 1 ;;
        tue) echo 2 ;;
        wed) echo 3 ;;
        thu) echo 4 ;;
        fri) echo 5 ;;
        sat) echo 6 ;;
        *)   echo "ERROR: unknown FINANCE_WEEKLY_DAY='$1' (use sun..sat)" >&2; exit 1 ;;
    esac
}

AUTH_HEADER="Authorization: Bearer ${API_AUTH_TOKEN}"
CURL_CMD="curl -fsS -m 280"

# Build the crontab
CRONTAB="${DIGEST_MINUTE} ${DIGEST_HOUR} * * * ${CURL_CMD} -X POST \"${API_BASE}/digests/run\" -H \"${AUTH_HEADER}\" >/proc/1/fd/1 2>&1
${FINANCE_SYNC_MINUTE} ${FINANCE_SYNC_HOUR} * * * ${CURL_CMD} -X POST \"${API_BASE}/finance/sync\" -H \"${AUTH_HEADER}\" >/proc/1/fd/1 2>&1"

if [ "${FINANCE_WEEKLY_ENABLED}" = "true" ]; then
    DOW="$(day_to_dow "${FINANCE_WEEKLY_DAY}")"
    CRONTAB="${CRONTAB}
${DIGEST_MINUTE} ${DIGEST_HOUR} * * ${DOW} ${CURL_CMD} -X POST \"${API_BASE}/digests/run-weekly\" -H \"${AUTH_HEADER}\" >/proc/1/fd/1 2>&1"
fi

printf '%s\n' "${CRONTAB}" > /etc/crontabs/root

echo "=== rendered crontab ==="
cat /etc/crontabs/root
echo "========================"

exec crond -f -l 8 -L /dev/stdout
