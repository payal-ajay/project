release: python manage.py migrate && python manage.py shell -c "from django.contrib.auth.models import User;
 User.objects.filter(username='admin').exists() or
User.objects.create_superuser('admin','admin@breatheesg.com','admin123')"
web: gunicorn esg_project.wsgi:application