#!/usr/bin/env bash
# exit on error
set -o errexit

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Create necessary directories
mkdir -p static staticfiles media
touch static/.gitkeep media/.gitkeep

# Clean up existing migrations
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete

# Create migration directories
mkdir -p users/migrations
touch users/migrations/__init__.py

# Make fresh migrations

python manage.py makemigrations

# Apply migrations

python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput --clear

# Create superuser
DJANGO_SUPERUSER_EMAIL=${DJANGO_SUPERUSER_EMAIL:-"admin@example.com"}
DJANGO_SUPERUSER_USERNAME=${DJANGO_SUPERUSER_USERNAME:-"admin"}
DJANGO_SUPERUSER_PASSWORD=${DJANGO_SUPERUSER_PASSWORD:-"adminpassword"}

python manage.py createsuperuser --noinput \
    --username $DJANGO_SUPERUSER_USERNAME \
    --email $DJANGO_SUPERUSER_EMAIL || true

echo "Build completed successfully!"
