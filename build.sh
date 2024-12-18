#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Clean up existing migrations
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete

# Create migration directories
mkdir -p users/migrations
touch users/migrations/__init__.py

# Make fresh migrations
python manage.py makemigrations users
python manage.py makemigrations

# Apply migrations
python manage.py migrate users
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser
DJANGO_SUPERUSER_EMAIL=${DJANGO_SUPERUSER_EMAIL:-"admin@example.com"}
DJANGO_SUPERUSER_USERNAME=${DJANGO_SUPERUSER_USERNAME:-"admin"}
DJANGO_SUPERUSER_PASSWORD=${DJANGO_SUPERUSER_PASSWORD:-"adminpassword"}

python manage.py createsuperuser --noinput \
    --username $DJANGO_SUPERUSER_USERNAME \
    --email $DJANGO_SUPERUSER_EMAIL || true
