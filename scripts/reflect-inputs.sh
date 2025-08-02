#!/usr/bin/env bash
set -euo pipefail

# Required environment variables: SYNC_PATH, OP_MODE, MODIFY_DATE
# Optional: GITHUB_TOKEN and GITHUB_REPOSITORY (provided automatically in GitHub Actions)

# Ensure yq pinned version is available
YQ_BIN=/usr/local/bin/yq
if ! command -v yq >/dev/null 2>&1; then
  echo "Installing yq..."
  curl -fsSL -o /tmp/yq_linux_amd64 https://github.com/mikefarah/yq/releases/download/v4.40.5/yq_linux_amd64
  sudo install -m 0755 /tmp/yq_linux_amd64 "$YQ_BIN"
fi
yq --version

WF=".github/workflows/enterprise-markdown-convert.yml"
if [[ ! -f "$WF" ]]; then
  echo "ERROR: workflow file missing at $WF" >&2
  exit 1
fi

# Backup for audit
cp "$WF" "${WF}.bak"

# Reflect runtime inputs into defaults
yq eval --inplace ".on.workflow_dispatch.inputs.sync_path.default = \"${SYNC_PATH}\"" "$WF"
yq eval --inplace ".on.workflow_dispatch.inputs.operation_mode.default = \"${OP_MODE}\"" "$WF"
yq eval --inplace ".on.workflow_dispatch.inputs.modify_date.default = \"${MODIFY_DATE}\"" "$WF"

echo "Diff after reflection:"
diff -u "${WF}.bak" "$WF" || true

# Prepare commit
git config user.name "self-reflector[bot]"
git config user.email "self-reflector@users.noreply.github.com"
git add "$WF"

# Save original remote for restore
ORIG_URL=$(git remote get-url origin)

# If GITHUB_TOKEN is provided, rewrite origin to use it for authenticated push
if [[ -n "${GITHUB_TOKEN-}" ]]; then
  if [[ -z "${GITHUB_REPOSITORY-}" ]]; then
    echo "WARNING: GITHUB_REPOSITORY not set; falling back to existing origin URL for push"
  else
    AUTH_URL="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
    git remote set-url origin "$AUTH_URL"
  fi
fi

# Commit & push (allow-empty ensures reflection commit always exists)
git commit --allow-empty -m "chore: reflect runtime inputs sync_path='${SYNC_PATH}' operation_mode='${OP_MODE}' modify_date='${MODIFY_DATE}'"
if ! git push; then
  echo "Warning: push failed. Check if workflow file modifications are permitted with current token." >&2
fi

# Restore original remote if mutated
if [[ -n "${GITHUB_TOKEN-}" ]]; then
  git remote set-url origin "$ORIG_URL"
fi
