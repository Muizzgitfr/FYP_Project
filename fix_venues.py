import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.models import ExamSchedule, ScheduleEntry, Venue, Enrollment
from collections import defaultdict

def fix_venues():
    latest_run = ExamSchedule.objects.order_by('-id').first()
    entries = list(ScheduleEntry.objects.filter(schedule=latest_run).select_related('section', 'slot', 'venue'))
    venues = list(Venue.objects.all())
    
    # Get student counts
    section_students = defaultdict(list)
    for e in Enrollment.objects.all().values('section_id', 'student_id'):
        section_students[e['section_id']].append(e['student_id'])
        
    venue_caps = {v.id: v.capacity for v in venues}
    slot_venue_usage = defaultdict(int)
    
    # Calculate current usage
    for entry in entries:
        all_students = section_students[entry.section_id]
        mid = len(all_students) // 2
        st_ids = all_students[:mid] if entry.part == "Part 1" else all_students[mid:]
        req_cap = len(st_ids) * 2
        
        slot_venue_usage[(entry.slot_id, entry.venue_id)] += req_cap

    changes = 0
    print("Fixing venue overflows...")
    
    for entry in entries:
        all_students = section_students[entry.section_id]
        mid = len(all_students) // 2
        st_ids = all_students[:mid] if entry.part == "Part 1" else all_students[mid:]
        req_cap = len(st_ids) * 2
        
        s_id = entry.slot_id
        v_id = entry.venue_id
        
        if slot_venue_usage[(s_id, v_id)] > venue_caps[v_id]:
            # This venue is over capacity. Find a new one in the SAME slot.
            for new_v in venues:
                if slot_venue_usage[(s_id, new_v.id)] + req_cap <= venue_caps[new_v.id]:
                    # Move it!
                    slot_venue_usage[(s_id, v_id)] -= req_cap
                    slot_venue_usage[(s_id, new_v.id)] += req_cap
                    entry.venue = new_v
                    changes += 1
                    break
                    
    if changes > 0:
        ScheduleEntry.objects.bulk_update(entries, ['venue'])
        print(f"Fixed {changes} venue assignments.")
    else:
        print("No venue overflows needed fixing (or couldn't be fixed).")

if __name__ == "__main__":
    fix_venues()
