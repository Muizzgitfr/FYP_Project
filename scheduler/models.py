from django.db import models

class Department(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)  # CS, BBA, LAW, etc.

    class Meta:
        db_table = 'departments'

    def __str__(self):
        return f"{self.code} - {self.name}"

class Course(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    credit_hours = models.IntegerField()  # heavy = 3+, light = 1-2
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='courses')

    class Meta:
        db_table = 'courses'

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def student_count(self):
        return self.enrollments.count()

class Venue(models.Model):
    name = models.CharField(max_length=100)
    capacity = models.IntegerField()
    building = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'venues'

    def __str__(self):
        return f"{self.name} (Cap: {self.capacity})"

class Student(models.Model):
    student_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='students')
    status = models.CharField(max_length=20, default='Active') # Active, Graduated, On Break

    class Meta:
        db_table = 'students'

    def __str__(self):
        return f"{self.student_id} - {self.name} ({self.status})"

class Teacher(models.Model):
    name = models.CharField(max_length=200)
    employee_id = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='teachers')

    class Meta:
        db_table = 'teachers'

    def __str__(self):
        return f"{self.name} ({self.employee_id})"

class Section(models.Model):
    """A course section/slot (max 50 students)"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=50) # e.g. "Section A"
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='sections')

    class Meta:
        db_table = 'sections'

    def __str__(self):
        return f"{self.course.code} - {self.name} ({self.teacher.name})"

class Enrollment(models.Model):
    """Link table for Student and Section enrollment"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='enrollments')
    enrollment_date = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'enrollments'
        unique_together = ('student', 'section')

    def __str__(self):
        return f"{self.student.student_id} -> {self.section.course.code} ({self.section.name})"

class ExamSlot(models.Model):
    """Represents a specific date + time block in the exam week"""
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_index = models.IntegerField()  # 0, 1, 2... for GA chromosome indexing

    class Meta:
        db_table = 'exam_slots'

    def __str__(self):
        return f"Slot {self.slot_index}: {self.date} {self.start_time}"

class ExamSchedule(models.Model):
    """One generated timetable instance"""
    name = models.CharField(max_length=100, default="Generated Schedule")
    created_at = models.DateTimeField(auto_now_add=True)
    fitness_score = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=False)

    class Meta:
        db_table = 'exam_schedules'

    def __str__(self):
        return f"{self.name} - {self.created_at.date()}"

class ScheduleEntry(models.Model):
    """One section part assigned to one slot and venue — child of ExamSchedule"""
    schedule = models.ForeignKey(ExamSchedule, on_delete=models.CASCADE, related_name='entries')
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE)
    slot = models.ForeignKey(ExamSlot, on_delete=models.CASCADE)
    part = models.CharField(max_length=10, default="Part 1") # To handle split sessions

    class Meta:
        db_table = 'schedule_entries'

    def __str__(self):
        return f"{self.section.course.code} {self.section.name} {self.part} in {self.venue.name}"