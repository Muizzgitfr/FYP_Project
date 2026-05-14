import os
import django
import random
import time
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.models import ExamSchedule, ScheduleEntry, Section, Venue, ExamSlot, Student, Enrollment

def optimize_run(schedule_id):
    print(f"Loading schedule for ID {schedule_id}...")
    schedule_obj = ExamSchedule.objects.get(id=schedule_id)
    entries = list(ScheduleEntry.objects.filter(schedule=schedule_obj).select_related('section', 'section__teacher', 'venue', 'slot'))
    
    if not entries:
        print("No schedule entries found.")
        return

    venues = list(Venue.objects.all())
    slots = list(ExamSlot.objects.all())
    
    # Pre-compute data
    sessions_dict = {}
    for entry in entries:
        sess = entry.section
        # Get enrollments for this section
        enrollments = Enrollment.objects.filter(section=sess).select_related('student')
        student_ids = [e.student_id for e in enrollments]
        
        sessions_dict[entry.id] = {
            'teacher_id': sess.teacher_id,
            'student_ids': student_ids,
            'student_count': len(student_ids),
            'obj': entry
        }

    chromosome = {entry.id: (entry.slot.slot_index, entry.venue.id) for entry in entries}
    
    def calculate_penalty(chrom):
        conflict_penalty = 0
        gap_penalty = 0
        venue_slot_occupancy = defaultdict(int)
        teacher_slot_usage = defaultdict(int)
        student_schedules = defaultdict(lambda: defaultdict(list))
        
        for eid, (s_idx, v_id) in chrom.items():
            sess = sessions_dict[eid]
            teacher_slot_usage[(s_idx, sess['teacher_id'])] += 1
            if teacher_slot_usage[(s_idx, sess['teacher_id'])] > 1: conflict_penalty += 1000
            venue_slot_occupancy[(s_idx, v_id)] += sess['student_count'] * 2 # Part logic (assuming half cap)
            for stid in sess['student_ids']:
                student_schedules[stid][s_idx // 5].append(s_idx)
                
        for (s, v), occ in venue_slot_occupancy.items():
            cap = next(ven.capacity for ven in venues if ven.id == v)
            if occ > cap: conflict_penalty += 500
            
        for stid, daily in student_schedules.items():
            for day, day_slots in daily.items():
                if len(day_slots) > 1:
                    day_slots.sort()
                    for i in range(len(day_slots)-1):
                        if day_slots[i] == day_slots[i+1]:
                            conflict_penalty += 10000 # High penalty for clash
                        else:
                            dist = day_slots[i+1] - day_slots[i]
                            if dist > 1:
                                gap_penalty += (dist - 1) * 10 # Soft penalty for gap
                                
        return conflict_penalty, gap_penalty

    best_chrom = chromosome.copy()
    best_conflict, best_gap = calculate_penalty(best_chrom)
    print(f"Initial: Conflicts={best_conflict}, Gaps={best_gap}")
    
    start_time = time.time()
    iterations = 0
    temperature = 100.0
    cooling_rate = 0.9995
    
    # 2 minutes SA
    while time.time() - start_time < 120 and temperature > 0.01: 
        eid = random.choice(list(sessions_dict.keys()))
        old_s_idx, old_v_id = best_chrom[eid]
        
        # Propose a new slot and venue
        new_s_idx = random.randint(0, len(slots)-1)
        new_v_id = random.choice(venues).id
        
        best_chrom[eid] = (new_s_idx, new_v_id)
        new_conflict, new_gap = calculate_penalty(best_chrom)
        
        # We want to minimize (conflict_penalty * 1000 + gap_penalty)
        cost_diff = (new_conflict * 1000 + new_gap) - (best_conflict * 1000 + best_gap)
        
        if cost_diff < 0 or random.random() < 2.71828 ** (-cost_diff / temperature):
            # Accept
            best_conflict, best_gap = new_conflict, new_gap
        else:
            # Reject
            best_chrom[eid] = (old_s_idx, old_v_id)
            
        temperature *= cooling_rate
        iterations += 1
        
        if iterations % 1000 == 0:
            print(f"Iter {iterations}: Conflicts={best_conflict}, Gaps={best_gap}, Temp={temperature:.2f}")

    print(f"Final: Conflicts={best_conflict}, Gaps={best_gap}")
    
    # Save back
    slot_objs = {s.slot_index: s for s in slots}
    venue_objs = {v.id: v for v in venues}
    
    for entry in entries:
        eid = entry.id
        s_idx, v_id = best_chrom[eid]
        entry.slot = slot_objs[s_idx]
        entry.venue = venue_objs[v_id]
        
    ScheduleEntry.objects.bulk_update(entries, ['slot', 'venue'])
    print("Optimization saved.")

if __name__ == "__main__":
    from django.db.models import Max
    latest_id = ExamSchedule.objects.aggregate(Max('id'))['id__max']
    if latest_id:
        optimize_run(latest_id)
