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

start: down up

fresh_start: purge build start
