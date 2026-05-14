import os
import django
import random
import pandas as pd
from datetime import date, time as dtime
from collections import defaultdict

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.models import Department, Course, Student, Enrollment, Venue, ExamSlot, Teacher, Section

DATA_PATH = "/Users/mac/Downloads/courses and students/"

def seed_data():
    print("🧹 Cleaning existing data...")
    Enrollment.objects.all().delete()
    Section.objects.all().delete()
    Teacher.objects.all().delete()
    Student.objects.all().delete()
    Course.objects.all().delete()
    Department.objects.all().delete()
    Venue.objects.all().delete()
    ExamSlot.objects.all().delete()

    print("🏢 Creating Departments and Courses from Excel...")
    dept_files = {
        "AI": "courses_AI.xlsx",
        "ANF": "courses_ANF.xlsx",
        "BBA": "courses_BBA.xlsx",
        "CS": "courses_CS.xlsx",
        "DS": "courses_DS.xlsx",
        "LAW": "courses_LAW.xlsx",
        "SE": "courses_SE.xlsx"
    }
    
    departments = {}
    all_courses = []
    
    for code, filename in dept_files.items():
        # Create Dept
        full_names = {
            "AI": "Artificial Intelligence", "ANF": "Accounting and Finance",
            "BBA": "Business Administration", "CS": "Computer Science",
            "DS": "Data Science", "LAW": "Law", "SE": "Software Engineering"
        }
        dept = Department.objects.create(name=full_names[code], code=code)
        departments[code] = dept
        
        # Read Courses
        df = pd.read_excel(os.path.join(DATA_PATH, filename))
        for _, row in df.iterrows():
            all_courses.append(Course(
                name=row['Course Name'],
                code=row['Course Code'],
                credit_hours=row.get('Credit Hours', 3),
                department=dept
            ))
    Course.objects.bulk_create(all_courses)
    all_courses = list(Course.objects.all())

    print("👨‍🏫 Creating 200 Teachers...")
    teachers = []
    for i in range(1, 201):
        dept = random.choice(list(departments.values()))
        teachers.append(Teacher(
            name=f"Professor {i}",
            employee_id=f"EMP{i:04d}",
            department=dept
        ))
    Teacher.objects.bulk_create(teachers)
    teachers = list(Teacher.objects.all())

    print("🏫 Creating Venues (Main Auditorium + 11 floors)...")
    venues = []
    
    # Explicitly add the Main Auditorium with 300 capacity (150 students with social distancing)
    venues.append(Venue(
        name="Main Auditorium",
        capacity=300,
        building="Main Campus Center"
    ))
    
    for floor in range(1, 12):
        for room in range(1, 11):
            room_number = floor * 100 + room
            venues.append(Venue(
                name=f"Room {room_number}",
                capacity=50, # Strict capacity of 50 for all regular rooms
                building=f"Building A - Floor {floor}"
            ))
    Venue.objects.bulk_create(venues)

    print("📅 Creating Exam Slots (1 Week, 5 slots per day)...")
    slots = []
    # Exact times requested: 9-11, 11:30-1:30, 2-4, 4:30-6:30, 7-9
    time_windows = [
        (dtime(9, 0), dtime(11, 0)),
        (dtime(11, 30), dtime(13, 30)),
        (dtime(14, 0), dtime(16, 0)),
        (dtime(16, 30), dtime(18, 30)),
        (dtime(19, 0), dtime(21, 0))
    ]
    for day in range(7):
        for t_idx, (start, end) in enumerate(time_windows):
            slots.append(ExamSlot(
                date=date(2026, 6, 1 + day),
                start_time=start,
                end_time=end,
                slot_index=day * 5 + t_idx
            ))
    ExamSlot.objects.bulk_create(slots)

    print("👤 Loading 6,000 Students from Excel...")
    df_students = pd.read_excel(os.path.join(DATA_PATH, "students_6000.xlsx"))
    student_objs = []
    dept_codes = list(departments.keys())
    
    # Create exact status distribution: 4000 Active, 1445 Graduated, 555 On Break
    statuses = ['Active'] * 4000 + ['Graduated'] * 1445 + ['On Break'] * 555
    random.shuffle(statuses)
    
    for i, row in df_students.iterrows():
        dept_code = random.choice(dept_codes)
        
        student_objs.append(Student(
            student_id=row['Student ID'],
            name=row['Full Name'],
            department=departments[dept_code],
            status=statuses[i]
        ))
    Student.objects.bulk_create(student_objs)
    all_students = list(Student.objects.all())

    print("📦 Creating Sections for each Course...")
    sections = []
    course_to_sections = defaultdict(list)
    for course in all_courses:
        for char in ['A', 'B']:
            sections.append(Section(
                course=course,
                name=f"Section {char}",
                teacher=random.choice(teachers)
            ))
    Section.objects.bulk_create(sections)
    for s in Section.objects.all():
        course_to_sections[s.course_id].append(s)

    print("📝 Enrolling ACTIVE Students into Sections (Random Model)...")
    active_students = [s for s in all_students if s.status == 'Active']
    enrollments = []
    count = 0
    for student in active_students:
        own_dept_courses = [c for c in all_courses if c.department_id == student.department_id]
        num_courses = random.randint(5, 7)
        selected_courses = random.sample(own_dept_courses, min(num_courses, len(own_dept_courses)))
        
        for course in selected_courses:
            sec = random.choice(course_to_sections[course.id])
            enrollments.append(Enrollment(student=student, section=sec))
            count += 1
            
        if len(enrollments) >= 2000:
            Enrollment.objects.bulk_create(enrollments, ignore_conflicts=True)
            enrollments = []

    if enrollments: Enrollment.objects.bulk_create(enrollments, ignore_conflicts=True)

    print(f"✨ Seeding Complete! Total Active Students Enrolled: {len(active_students)}")

if __name__ == "__main__":
    seed_data()
