#!/bin/bash

cd /home/ec2-user/app

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_DEFAULT_REGION:-ap-southeast-1}

log "Signing in to ECR"
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

log "Pulling images"
docker compose -f docker-compose.prod.yml --env-file .env --env-file .image_uri_env pull
log "Bringing stack up"
docker compose -f docker-compose.prod.yml --env-file .env --env-file .image_uri_env up -d --remove-orphans

log "Deployment complete."
exit 0
