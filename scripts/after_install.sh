#!/bin/bash

cd /home/ec2-user/app

log "Pulling images"
docker compose -f docker-compose.prod.yml --env-file .env --env-file .image_uri_env pull
log "Bringing stack up"
docker compose -f docker-compose.prod.yml --env-file .env --env-file .image_uri_env up -d --remove-orphans

log "Deployment complete."
exit 0
