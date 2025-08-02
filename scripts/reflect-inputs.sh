#!/usr/bin/env bash
set -euo pipefail

# Required environment variables: SYNC_PATH, OP_MODE, MODIFY_DATE
# Optional: WORKFLOW_TOKEN (preferred for mutating workflow YAML), fallback to GITHUB_TOKEN.
#             GITHUB_REPOSITORY must be set (provided by GitHub Actions automatically).

# --- Validate inputs --------------------------------------------------------
: "${SYNC_PATH:?Environment variable SYNC_PATH is required}"
: "${OP_MODE:?Environment variable OP_MODE is required}"
: "${MODIFY_DATE:?Environment variable MODIFY_DATE is required}"

# Choose token: prefer WORKFLOW_TOKEN, then GITHUB_TOKEN.
AUTH_TOKEN="${WORKFLOW_TOKEN:-${GITHUB_TOKEN-}}"
if [[ -z "${AUTH_TOKEN:-}" ]]; then
  echo "WARNING: No WORKFLOW_TOKEN or GITHUB_TOKEN provided; push may fail if authentication is required."
fi

# --- Ensure yq is installed (deterministic pinned version) -----------------
YQ_BIN=/usr/local/bin/yq
if ! command -v yq >/dev/null 2>&1; then
  echo "Installing yq v4.40.5..."
  curl -fsSL -o /tmp/yq_linux_amd64 \
    https://github.com/mikefarah/yq/releases/download/v4.40.5/yq_linux_amd64
  sudo install -m 0755 /tmp/yq_linux_amd64 "$YQ_BIN"
fi
yq --version

# --- Reflect into workflow --------------------------------------------------
WF=".github/workflows/enterprise-markdown-convert.yml"
if [[ ! -f "$WF" ]]; then
  echo "ERROR: workflow file missing at $WF" >&2
  exit 1
fi

# Backup for audit/troubleshooting
cp "$WF" "${WF}.bak"

# Safely replace the defaults; escape values to avoid YAML injection issues
escaped_sync_path=$(printf '%s' "$SYNC_PATH" | sed 's/"/\\"/g')
escaped_op_mode=$(printf '%s' "$OP_MODE" | sed 's/"/\\"/g')
escaped_modify_date=$(printf '%s' "$MODIFY_DATE" | sed 's/"/\\"/g')

yq eval --inplace ".on.workflow_dispatch.inputs.sync_path.default = \"${escaped_sync_path}\"" "$WF"
yq eval --inplace ".on.workflow_dispatch.inputs.operation_mode.default = \"${escaped_op_mode}\"" "$WF"
yq eval --inplace ".on.workflow_dispatch.inputs.modify_date.default = \"${escaped_modify_date}\"" "$WF"

echo "Diff after reflection:"
diff -u "${WF}.bak" "$WF" || true

# --- Commit logic -----------------------------------------------------------
git config user.name "self-reflector[bot]"
git config user.email "self-reflector@users.noreply.github.com"
git add "$WF"

# Preserve original origin to restore later
ORIG_URL=$(git remote get-url origin || true)

# If we have an auth token and repository context, rewrite remote for push
if [[ -n "${AUTH_TOKEN:-}" && -n "${GITHUB_REPOSITORY-}" ]]; then
  AUTH_URL="https://x-access-token:${AUTH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
  git remote set-url origin "$AUTH_URL"
fi

# Always create reflection commit (allow-empty)
git commit --allow-empty -m "chore: reflect runtime inputs sync_path='${SYNC_PATH}' operation_mode='${OP_MODE}' modify_date='${MODIFY_DATE}'"

if ! git push --no-verify; then
  echo "Warning: push failed. Check token permissions or whether workflow file updates are allowed." >&2
fi

# Restore original remote if we mutated it
if [[ -n "${AUTH_TOKEN:-}" && -n "${ORIG_URL:-}" ]]; then
  git remote set-url origin "$ORIG_URL"
fi
