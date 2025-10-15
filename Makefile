include .env

up:
	docker compose up --watch

down:
	docker compose down --remove-orphans

build:
	uv lock && docker compose build

purge:
	docker compose down -v --remove-orphans

shell:
	docker compose exec backend uv run --no-default-groups --directory ./apps manage.py shell

lint:
	docker compose run --rm lint

ecr_build_push:
	aws ecr get-login-password --region ${AWS_ECR_REGION} | docker login --username AWS --password-stdin ${AWS_ACC_ID}.dkr.ecr.${AWS_ECR_REGION}.amazonaws.com
	docker build -t ${AWS_ACC_ID}.dkr.ecr.${AWS_ECR_REGION}.amazonaws.com/${AWS_ECR_REPO}:latest --provenance=false --platform linux/amd64 .
	docker push ${AWS_ACC_ID}.dkr.ecr.${AWS_ECR_REGION}.amazonaws.com/${AWS_ECR_REPO}:latest

quick_start: down up

start: down quick_start

fresh_start: purge build start
