#!/usr/bin/env bash
# Forced command for the `ci` SSH deploy key (see ~ci/.ssh/authorized_keys and
# docs/operations.md's "SSH deploy" section). sshd runs this in place of
# whatever the client sent, with the client's actual request in
# SSH_ORIGINAL_COMMAND — so this is the only thing a leaked deploy key can
# trigger, and only in the exact shape checked below.
set -euo pipefail

if [[ ! "${SSH_ORIGINAL_COMMAND:-}" =~ ^deploy\ ([a-f0-9]{12})$ ]]; then
    echo "rejected: ${SSH_ORIGINAL_COMMAND:-<empty>}" >&2
    exit 1
fi

cd /opt/apps/disp
exec ./scripts/deploy.sh "${BASH_REMATCH[1]}"
