#!/bin/sh
# Run inside a freshly built image with test configuration, without live data.
set -eu

python manage.py check
python scripts/check_deployment.py --validate-config
python manage.py collectstatic --noinput
python manage.py shell -c 'from django.contrib.staticfiles.storage import staticfiles_storage; names = ("css/styles.css", "admin/css/base.css"); assert all(staticfiles_storage.exists(staticfiles_storage.stored_name(name)) for name in names), "Gesammelte Stylesheets fehlen"; print("Release-Image und Stylesheets geprüft")'
