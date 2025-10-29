.PHONY: up down logs migrate makemigrations shell createsuperuser

up:
\tdocker compose up --build

down:
\tdocker compose down

logs:
\tdocker compose logs -f web

migrate:
\tdocker compose exec web python manage.py migrate

makemigrations:
\tdocker compose exec web python manage.py makemigrations

shell:
\tdocker compose exec web python manage.py shell

createsuperuser:
\tdocker compose exec web python manage.py createsuperuser
