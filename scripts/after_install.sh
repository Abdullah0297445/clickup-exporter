#!/bin/bash

COMPOSE_FILE="/home/ec2-user/app/docker-compose.prod.yml"

log "Pulling images"
docker compose -f "${COMPOSE_FILE}" pull
log "Bringing stack up"
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

log "Deployment complete."
exit 0
