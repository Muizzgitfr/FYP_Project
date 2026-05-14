from django.shortcuts import render
from .models import Student, Enrollment, ScheduleEntry, ExamSchedule, Section
from django.db.models import Prefetch

def student_schedule(request):
    student_id = request.GET.get('student_id', '').strip()
    student = None
    enrollments = []
    exam_entries = []
    error = None

    if student_id:
        try:
            student = Student.objects.get(student_id=student_id)
            # Get registered sections
            enrollments = Enrollment.objects.filter(student=student).select_related('section__course', 'section__teacher')
            
            # Get latest active schedule
            latest_schedule = ExamSchedule.objects.filter(is_active=True).order_by('-created_at').first()
            if latest_schedule:
                # Find exam entries for this student's sections
                # We need to filter entries where the student is in the Part
                all_entries = ScheduleEntry.objects.filter(
                    schedule=latest_schedule,
                    section__enrollments__student=student
                ).select_related('section__course', 'section__teacher', 'venue', 'slot').order_by('slot__date', 'slot__start_time')
                
                # Filter by part logic
                for entry in all_entries:
                    all_students = list(Student.objects.filter(enrollments__section=entry.section).order_by('id').values_list('student_id', flat=True))
                    mid = len(all_students) // 2
                    if entry.part == "Part 1":
                        p_students = all_students[:mid]
                    else:
                        p_students = all_students[mid:]
                    
                    if student.student_id in p_students:
                        exam_entries.append(entry)
            else:
                error = "No active exam schedule found."
        except Student.DoesNotExist:
            error = f"Student with ID '{student_id}' not found."

    return render(request, 'scheduler/student_schedule.html', {
        'student': student,
        'enrollments': enrollments,
        'exam_entries': exam_entries,
        'error': error,
        'student_id': student_id
    })

from collections import defaultdict
from datetime import datetime

def gap_report(request):
    latest_schedule = ExamSchedule.objects.filter(is_active=True).order_by('-created_at').first()
    # If no active, just get latest
    if not latest_schedule:
        latest_schedule = ExamSchedule.objects.order_by('-created_at').first()
        
    error = None
    gap_issues = []
    
    if latest_schedule:
        entries = list(ScheduleEntry.objects.filter(schedule=latest_schedule).select_related('section__course', 'venue', 'slot', 'section'))
        
        # Pre-fetch enrollments
        section_students = defaultdict(list)
        for enr in Enrollment.objects.all().select_related('student'):
            section_students[enr.section_id].append(enr.student)
            
        student_sessions = defaultdict(list)
        for entry in entries:
            all_students = section_students[entry.section_id]
            mid = len(all_students) // 2
            if entry.part == "Part 1":
                p_students = all_students[:mid]
            else:
                p_students = all_students[mid:]
                
            for student in p_students:
                student_sessions[student].append(entry)
                
        for student, sess_list in student_sessions.items():
            day_slots = defaultdict(list)
            for sess in sess_list:
                day_slots[sess.slot.date].append(sess)
                
            for sdate, daily_entries in day_slots.items():
                if len(daily_entries) > 1:
                    daily_entries.sort(key=lambda x: x.slot.start_time)
                    for i in range(len(daily_entries)-1):
                        e1 = daily_entries[i]
                        e2 = daily_entries[i+1]
                        t1 = datetime.combine(sdate, e1.slot.end_time)
                        t2 = datetime.combine(sdate, e2.slot.start_time)
                        gap_hours = (t2 - t1).total_seconds() / 3600.0
                        
                        if gap_hours > 3.5: # More than 1 slot break
                            gap_issues.append({
                                'student': student,
                                'date': sdate,
                                'exam1': e1,
                                'exam2': e2,
                                'gap_hours': round(gap_hours, 1)
                            })
                            
        # Sort by gap hours descending
        gap_issues.sort(key=lambda x: x['gap_hours'], reverse=True)
    else:
        error = "No schedule found."
        
    return render(request, 'scheduler/gap_report.html', {
        'schedule': latest_schedule,
        'gap_issues': gap_issues,
        'error': error,
        'total_gaps': len(gap_issues)
    })

