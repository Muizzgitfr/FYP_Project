import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.models import ExamSchedule, ScheduleEntry, ExamSlot, Enrollment, Section
from collections import defaultdict

def fix_student_gaps(student_id):
    latest_run = ExamSchedule.objects.order_by('-id').first()
    if not latest_run:
        print("No schedule found.")
        return

    entries = list(ScheduleEntry.objects.filter(schedule=latest_run).select_related('section', 'slot'))
    slots = list(ExamSlot.objects.order_by('slot_index'))
    
    # 1. Build clash tracking
    print("Building tracking matrices...")
    slot_student_map = defaultdict(set)
    section_student_map = {}
    
    enrollments = Enrollment.objects.all().select_related('student', 'section')
    for e in enrollments:
        if e.section_id not in section_student_map:
            section_student_map[e.section_id] = set()
        section_student_map[e.section_id].add(e.student.student_id)
        
    for entry in entries:
        students = section_student_map.get(entry.section_id, set())
        slot_student_map[entry.slot.slot_index].update(students)

    # 2. Find student's entries
    student_entries = []
    for entry in entries:
        if student_id in section_student_map.get(entry.section_id, set()):
            student_entries.append(entry)

    if not student_entries:
        print(f"No exams found for {student_id}")
        return

    # Group by day
    daily_entries = defaultdict(list)
    for entry in student_entries:
        day = entry.slot.slot_index // 5
        daily_entries[day].append(entry)

    changes_made = 0
    print(f"\nAnalyzing gaps for {student_id}...")
    for day, day_ents in daily_entries.items():
        if len(day_ents) > 1:
            day_ents.sort(key=lambda e: e.slot.slot_index)
            print(f"Day {day}: {[e.slot.start_time.strftime('%H:%M') for e in day_ents]}")
            
            # Try to compress
            for i in range(1, len(day_ents)):
                prev = day_ents[i-1]
                curr = day_ents[i]
                
                dist = curr.slot.slot_index - prev.slot.slot_index
                if dist > 1:
                    print(f"  Found gap between {prev.section.course.name} and {curr.section.course.name}")
                    
                    # Try to move curr to prev.slot.slot_index + 1
                    target_idx = prev.slot.slot_index + 1
                    target_slot = slots[target_idx]
                    
                    # Check if target_slot is safe for all students in curr.section
                    curr_students = section_student_map.get(curr.section_id, set())
                    target_students = slot_student_map[target_idx]
                    
                    overlap = curr_students.intersection(target_students)
                    if not overlap:
                        print(f"    -> Can safely move {curr.section.course.name} to {target_slot.start_time}")
                        
                        # Update maps
                        slot_student_map[curr.slot.slot_index] -= curr_students
                        slot_student_map[target_idx].update(curr_students)
                        
                        curr.slot = target_slot
                        curr.save()
                        changes_made += 1
                    else:
                        print(f"    -> Cannot move. It would create a clash for {len(overlap)} other students!")

    print(f"\nOptimization complete. {changes_made} changes made.")

if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else 'STU-01511'
    fix_student_gaps(sid)
