#!/usr/bin/env bash
# Pulls and redeploys a new disp/disp-web image tag (api, worker, web —
# built and tagged together in .github/workflows/deploy.yml), invoked over
# SSH from that workflow's deploy job. Rolls back to the previously-deployed
# tag if the post-deploy health check fails.
#
# Usage: ./scripts/deploy.sh <image-tag>
#
# Run from the app directory, which must be a git checkout of this repo on
# `prod` (docker-compose.yml, docker-compose.prod.yml and .env must already
# exist there — see docs/operations.md's "SSH deploy" section for one-time
# host setup). Never runs migrations: those stay a manual step per "First
# deploy" in docs/operations.md.
set -euo pipefail

# ff-only, and before anything else runs: a new image tag often ships
# alongside compose/script changes (this file included), so the host's
# checkout needs to match before recreate() reads docker-compose*.yml. A
# host with local drift should fail loudly here rather than merge silently.
git pull --ff-only

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
    # api publishes no host port (Traefik/edge-network only, see
    # docker-compose.yml) — probe /health from inside the container's own
    # network namespace instead of curling it from the host.
    if docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T api \
        python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"; then
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
