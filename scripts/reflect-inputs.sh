#!/usr/bin/env bash
set -euo pipefail

# Required environment variables: SYNC_PATH, OP_MODE, MODIFY_DATE

# Ensure yq v4.40.5 is installed
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

# Backup for visibility
cp "$WF" "${WF}.bak"

# Replace runtime inputs into defaults
yq eval --inplace ".on.workflow_dispatch.inputs.sync_path.default = \"${SYNC_PATH}\"" "$WF"
yq eval --inplace ".on.workflow_dispatch.inputs.operation_mode.default = \"${OP_MODE}\"" "$WF"
yq eval --inplace ".on.workflow_dispatch.inputs.modify_date.default = \"${MODIFY_DATE}\"" "$WF"

echo "Diff after reflection:"
diff -u "${WF}.bak" "$WF" || true

# Commit reflection (allow-empty)
git config user.name "self-reflector[bot]"
git config user.email "self-reflector@users.noreply.github.com"

git add "$WF"

# Determine push method: if GIT_PUSH_TOKEN env var present (PAT), use it for auth, else rely on existing remote
if [[ -n "${GIT_PUSH_TOKEN-}" ]]; then
  # Replace origin URL to embed token safely without leaking in logs
  ORIG_URL=$(git remote get-url origin)
  AUTH_URL=$(echo "$ORIG_URL" | sed -E "s#https://#https://${GIT_PUSH_TOKEN}@#")
  git remote set-url origin "$AUTH_URL"
fi

git commit --allow-empty -m "chore: reflect runtime inputs sync_path='${SYNC_PATH}' operation_mode='${OP_MODE}' modify_date='${MODIFY_DATE}'"

# Push; if using PAT, reset remote after
if ! git push; then
  echo "Warning: push failed. Inspect permissions or token." >&2
fi

if [[ -n "${GIT_PUSH_TOKEN-}" ]]; then
  # restore remote to original (remove embedded token)
  git remote set-url origin "$ORIG_URL"
fi
