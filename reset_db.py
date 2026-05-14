import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

tables = [
    'enrollments', 
    'schedule_entries', 
    'sections', 
    'teachers', 
    'students', 
    'courses', 
    'departments', 
    'venues', 
    'exam_slots', 
    'exam_schedules',
    'django_migrations'
]

with connection.cursor() as cursor:
    print("🗑️ Dropping tables...")
    for table in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            print(f"  - Dropped {table}")
        except Exception as e:
            print(f"  - Error dropping {table}: {e}")
    
    # Also drop the old prefixed ones just in case
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'scheduler_%';")
    old_tables = [row[0] for row in cursor.fetchall()]
    for table in old_tables:
        cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
        print(f"  - Dropped old table {table}")

print("✨ Database reset complete!")
