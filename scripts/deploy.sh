#!/usr/bin/env bash
# Pulls and redeploys a new disp/disp-web image tag (api, worker, web —
# built and tagged together in .github/workflows/deploy.yml), invoked over
# SSH from that workflow's deploy job. Rolls back to the previously-deployed
# tag if the post-deploy health check fails.
#
# Usage: ./scripts/deploy.sh <image-tag>
#
# Run from the app directory (docker-compose.yml, docker-compose.prod.yml and
# .env must already exist there — see docs/operations.md's "SSH deploy"
# section for one-time host setup). Never runs migrations: those stay a
# manual step per "First deploy" in docs/operations.md.
set -euo pipefail

new_tag="${1:?image tag required}"

previous_tag="$(grep '^IMAGE_TAG=' .env 2>/dev/null | cut -d= -f2 || true)"

set_image_tag() {
    if grep -q '^IMAGE_TAG=' .env 2>/dev/null; then
        sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$1/" .env
    else
        echo "IMAGE_TAG=$1" >> .env
    fi
}

recreate() {
    docker compose -f docker-compose.yml -f docker-compose.prod.yml pull api worker web
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api worker web
}

echo "Deploying $new_tag (previously: ${previous_tag:-none})"
set_image_tag "$new_tag"
recreate

healthy=0
for _ in 1 2 3 4 5 6; do
    if curl -sf http://localhost:8000/health >/dev/null; then
        healthy=1
        break
    fi
    sleep 5
done

if [[ "$healthy" -eq 1 ]]; then
    echo "Deploy of $new_tag succeeded"
    exit 0
fi

echo "Health check failed after deploying $new_tag" >&2
if [[ -n "$previous_tag" ]]; then
    echo "Rolling back to $previous_tag" >&2
    set_image_tag "$previous_tag"
    recreate
else
    echo "No previous tag recorded, nothing to roll back to" >&2
fi
exit 1
