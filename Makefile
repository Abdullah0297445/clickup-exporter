include .env

up:
	docker compose up --watch

down:
	docker compose down --remove-orphans

build:
	uv lock && docker compose build

purge:
	docker compose down -v --remove-orphans

lint:
	docker compose run --rm lint

quick_start: down up

start: down quick_start

fresh_start: purge build start
