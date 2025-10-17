#!/bin/bash

cd /home/ec2-user/app

log "Pulling images"
docker compose -f docker-compose.prod.yml pull
log "Bringing stack up"
docker compose -f docker-compose.prod.yml --env-file .env up -d --remove-orphans

log "Deployment complete."
exit 0
