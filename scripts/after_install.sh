#!/bin/bash

cd /home/ec2-user/app

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_DEFAULT_REGION:-ap-southeast-1}

log "Signing in to ECR"
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

log "Stopping current stack"
docker compose -f docker-compose.prod.yml --env-file .env --env-file .image_uri_env down --remove-orphans
log "Pulling images"
docker compose -f docker-compose.prod.yml --env-file .env --env-file .image_uri_env pull
log "Bringing new stack up"
docker compose -f docker-compose.prod.yml --env-file .env --env-file .image_uri_env up -d

log "Deployment complete."
exit 0
