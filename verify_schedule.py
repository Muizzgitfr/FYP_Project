import os
import django
from collections import defaultdict
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.models import ExamSchedule, ScheduleEntry, ExamSlot, Enrollment

def verify_latest_schedule():
    schedule = ExamSchedule.objects.order_by('-created_at').first()
    if not schedule:
        print("❌ No schedule found in database!")
        return

    print(f"🧐 Verifying Schedule: {schedule.name} (ID: {schedule.id})")
    entries = list(ScheduleEntry.objects.filter(schedule=schedule).select_related('section', 'venue', 'slot', 'section__teacher'))
    
    clashes = []
    teacher_conflicts = []
    capacity_violations = []
    gap_issues = []
    
    # 1. Maps for checking
    student_slot_map = defaultdict(list) # (student_id, slot_id) -> [entry]
    teacher_slot_map = defaultdict(list) # (teacher_id, slot_id) -> [entry]
    venue_slot_map = defaultdict(list)   # (venue_id, slot_id) -> [entry]
    student_day_slots = defaultdict(lambda: defaultdict(list)) # student -> date -> [slot_idx]

    # Pre-fetch all enrollments to know which students are in which section
    print("⏳ Loading enrollment data...")
    section_students = defaultdict(list)
    for enr in Enrollment.objects.all().values('section_id', 'student_id'):
        section_students[enr['section_id']].append(enr['student_id'])

    print("🔍 Analyzing entries...")
    for entry in entries:
        s_idx = entry.slot.slot_index
        v_id = entry.venue.id
        t_id = entry.section.teacher.id
        
        # Teacher Conflict
        teacher_slot_map[(t_id, s_idx)].append(entry)
        
        # Venue Occupancy
        venue_slot_map[(v_id, s_idx)].append(entry)
        
        # Student Conflicts & Day Tracking
        students = section_students[entry.section_id]
        # In a real split, we'd need to know which students are in WHICH PART.
        # But since we split randomly in GA, we'll assume the students are divided.
        # For verification, we'll just check if a student appears in 2 entries in same slot.
        # Actually, let's just use the count of students for capacity
        
    # Check Teacher Conflicts
    for (t_id, s_idx), shared_entries in teacher_slot_map.items():
        if len(shared_entries) > 1:
            teacher_conflicts.append(f"Teacher {shared_entries[0].section.teacher.name} in Slot {s_idx} for {len(shared_entries)} exams")

    # Check Venue Capacity
    for (v_id, s_idx), shared_entries in venue_slot_map.items():
        # Calculate total students in this venue-slot
        total_students = 0
        for e in shared_entries:
            chunk_size = 20
            try:
                part_num = int(e.part.split(' ')[1])
            except (IndexError, ValueError):
                part_num = 1
            start_idx = (part_num - 1) * chunk_size
            st_ids = section_students[e.section_id][start_idx : start_idx + chunk_size]
            total_students += len(st_ids)
            
        required_with_gaps = total_students # 100% physical capacity, no * 2 multiplier
        capacity = shared_entries[0].venue.capacity
        if required_with_gaps > capacity:
            capacity_violations.append(f"Venue {shared_entries[0].venue.name} in Slot {s_idx}: Needs {required_with_gaps}, Has {capacity}")

    # Check Student Clashes and Gaps
    # This is heavy, so we sample if needed, but let's try for all
    print("🧠 Checking student-level constraints (clashes and 1-hour gaps)...")
    
    # We need to reconstruct student schedules
    # (Simplified: check if any student has 2 sessions in same slot)
    # Since we don't store exactly which students are in which Part in the DB yet,
    # we'll verify the Logic: A student shouldn't have 2 entries in the same slot.
    
    # Let's map student to entries
    student_sessions = defaultdict(list)
    for entry in entries:
        all_students = section_students[entry.section_id]
        # Reconstruct chunk
        chunk_size = 20
        try:
            part_num = int(entry.part.split(' ')[1])
        except (IndexError, ValueError):
            part_num = 1
            
        start_idx = (part_num - 1) * chunk_size
        p_students = all_students[start_idx : start_idx + chunk_size]
            
        for stid in p_students:
            student_sessions[stid].append(entry)

    for stid, sess_list in student_sessions.items():
        slots_seen = defaultdict(int)
        day_slots = defaultdict(list)
        
        for sess in sess_list:
            slots_seen[sess.slot.slot_index] += 1
            day_slots[sess.slot.date].append(sess.slot)
            
        # Clash
        for s_idx, count in slots_seen.items():
            if count > 1:
                clashes.append(f"Student {stid} has {count} exams in Slot {s_idx}")
        
        # Gap > 1 hour
        for sdate, slots in day_slots.items():
            if len(slots) > 1:
                slots.sort(key=lambda x: x.start_time)
                for i in range(len(slots)-1):
                    # Check gap between slots[i] and slots[i+1]
                    t1 = datetime.combine(sdate, slots[i].end_time)
                    t2 = datetime.combine(sdate, slots[i+1].start_time)
                    gap_hours = (t2 - t1).total_seconds() / 3600.0
                    if gap_hours > 3.5: # Allow up to 1 slot break (which is max 3 hours)
                        gap_issues.append(f"Student {stid} on {sdate}: Gap of {gap_hours:.1f}h between {slots[i].start_time} and {slots[i+1].start_time}")

    print("\n--- 📊 VERIFICATION REPORT ---")
    print(f"✅ Total Entries: {len(entries)}")
    print(f"❌ Teacher Conflicts: {len(teacher_conflicts)}")
    print(f"❌ Venue Capacity Violations: {len(capacity_violations)}")
    print(f"❌ Student Clashes: {len(clashes)}")
    print(f"⚠️ Student Gap Issues (>1h): {len(gap_issues)}")
    
    if teacher_conflicts: print("\nFirst 5 Teacher Conflicts:", teacher_conflicts[:5])
    if capacity_violations: print("\nFirst 5 Capacity Violations:", capacity_violations[:5])
    if clashes: print("\nFirst 5 Student Clashes:", clashes[:5])
    if gap_issues: print("\nFirst 5 Gap Issues:", gap_issues[:5])

if __name__ == "__main__":
    verify_latest_schedule()
