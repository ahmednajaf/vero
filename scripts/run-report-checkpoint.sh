#!/usr/bin/env bash
# Original, frozen 20-company development cohort. The CLI enforces 5 -> 20.
# This script cannot start a 50/100/200-company run.
set -euo pipefail
cd "$(dirname "$0")/../backend"

resume_args=()
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--resume" ) ]]; then
  echo 'Usage: bash scripts/run-report-checkpoint.sh [--resume]' >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then resume_args=(--resume); fi

company_args=()
for company_number in {1..20}; do
  printf -v company_id '01900000-0000-4000-8000-%012d' "$company_number"
  company_args+=(--company "$company_id")
done

export LLM_TIMEOUT_SECONDS=300
export LLM_MAX_OUTPUT_TOKENS=2048
export PARSE_TIMEOUT_SECONDS=900
export PIPELINE_COMPANY_WORKERS=1
export PIPELINE_FAIL_FAST=true

exec .venv/bin/python -m app.cli run-pipeline \
  --year 2025 --observation-year 2024 --limit 20 --top-k 1 \
  "${company_args[@]}" "${resume_args[@]}"
