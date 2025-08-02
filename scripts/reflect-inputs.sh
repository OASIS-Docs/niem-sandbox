#!/usr/bin/env bash
set -euo pipefail

# Require these to be provided as environment variables:
# SYNC_PATH, OP_MODE, MODIFY_DATE

# Ensure yq is installed (pinned version)
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

# Replace default input values in-place
yq eval --inplace ".on.workflow_dispatch.inputs.sync_path.default = \"${SYNC_PATH}\"" "$WF"
yq eval --inplace ".on.workflow_dispatch.inputs.operation_mode.default = \"${OP_MODE}\"" "$WF"
yq eval --inplace ".on.workflow_dispatch.inputs.modify_date.default = \"${MODIFY_DATE}\"" "$WF"

echo "Diff after reflection:"
diff -u "${WF}.bak" "$WF" || true

# Commit unconditionally (allow-empty if no change)
git config user.name "self-reflector[bot]"
git config user.email "self-reflector@users.noreply.github.com"
git add "$WF"
git commit --allow-empty -m "chore: reflect runtime inputs sync_path='${SYNC_PATH}' operation_mode='${OP_MODE}' modify_date='${MODIFY_DATE}'"
git push
