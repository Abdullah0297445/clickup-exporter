include .env

up:
	docker compose -f docker-compose.prod.yml -f docker-compose.yml up --watch

down:
	docker compose -f docker-compose.prod.yml -f docker-compose.yml down --remove-orphans

build:
	uv lock && docker compose -f docker-compose.prod.yml -f docker-compose.yml build

purge:
	docker compose -f docker-compose.prod.yml -f docker-compose.yml down -v --remove-orphans

shell:
	docker compose -f docker-compose.prod.yml -f docker-compose.yml exec backend uv run --no-default-groups --directory ./apps manage.py shell

lint:
	docker compose -f docker-compose.prod.yml -f docker-compose.yml run --rm lint

ecr_build_push:
	aws ecr get-login-password --region ${AWS_ECR_REGION} | docker login --username AWS --password-stdin ${AWS_ACC_ID}.dkr.ecr.${AWS_ECR_REGION}.amazonaws.com
	docker build -t ${AWS_ACC_ID}.dkr.ecr.${AWS_ECR_REGION}.amazonaws.com/${AWS_ECR_REPO}:latest --provenance=false --platform linux/amd64 .
	docker push ${AWS_ACC_ID}.dkr.ecr.${AWS_ECR_REGION}.amazonaws.com/${AWS_ECR_REPO}:latest

quick_start: down up

start: down quick_start

fresh_start: purge build start
