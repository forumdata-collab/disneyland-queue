#!/bin/bash
# HK Disneyland wait times: fetch → deploy to CF Pages (disneyland.we1co.me)
# Silent on success (cron no_agent: empty stdout = no delivery). Prints only on failure.
cd /home/ubuntu/disneyland-map || exit 1
export $(grep -E "^(CF_WORKERS_TOKEN|CF_ACCOUNT_ID)=" /home/ubuntu/.hermes/.env | xargs) 2>/dev/null

OUT=$(/home/ubuntu/.hermes/hermes-agent/venv/bin/python3 fetch_hkdl.py 2>&1)
RC=$?
if [ $RC -ne 0 ]; then
  echo "DISNEY FETCH FAIL: $OUT"
  exit 1
fi

DEPLOY=$(CLOUDFLARE_API_TOKEN=$CF_WORKERS_TOKEN npx wrangler pages deploy . --project-name disneyland-queue --branch=main 2>&1)
if [ $? -ne 0 ]; then
  echo "DISNEY DEPLOY FAIL: $DEPLOY"
  exit 1
fi
# success → silent
exit 0