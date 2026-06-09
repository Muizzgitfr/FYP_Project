import os
import django
import random
import time
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.models import ExamSchedule, ScheduleEntry, ExamSlot, Venue, Enrollment

def fast_optimize(schedule_id=None):
    if schedule_id:
        latest_run = ExamSchedule.objects.get(id=schedule_id)
    else:
        latest_run = ExamSchedule.objects.order_by('-id').first()
    if not latest_run:
        print("No schedule found.")
        return

    print(f"Loading Schedule ID: {latest_run.id}")
    entries = list(ScheduleEntry.objects.filter(schedule=latest_run).select_related('section', 'slot', 'venue'))
    slots = list(ExamSlot.objects.order_by('slot_index'))
    venues = list(Venue.objects.all())
    
    venue_caps = {v.id: v.capacity for v in venues}
    slot_ids = [s.slot_index for s in slots]
    auditorium_id = next((v.id for v in venues if v.name == "Main Auditorium"), None)
    
    # 1. Build fast lookup maps
    print("Pre-computing student matrices...")
    enrollments = Enrollment.objects.all().select_related('student', 'section')
    section_students = defaultdict(list)
    for e in enrollments:
        section_students[e.section_id].append(e.student_id)
        
    # State tracking
    chrom = {} # entry_id -> (slot_idx, venue_id)
    entry_data = {} # entry_id -> {teacher_id, student_ids, req_cap}
    
    # Trackers for O(1) delta calculation
    teacher_slot_counts = defaultdict(int) # (slot_idx, teacher_id) -> count
    venue_slot_usage = defaultdict(int)    # (slot_idx, venue_id) -> total_students
    student_slot_counts = defaultdict(int) # (student_id, slot_idx) -> count
    student_daily_slots = defaultdict(lambda: defaultdict(list)) # (student_id) -> day -> list of slots
    
    for entry in entries:
        s_idx = entry.slot.slot_index
        v_id = entry.venue.id
        chrom[entry.id] = (s_idx, v_id)
        
        all_students = section_students[entry.section_id]
        
        # Reconstruct exactly which students are in this Part
        chunk_size = 20
        try:
            part_num = int(entry.part.split(' ')[1])
        except (IndexError, ValueError):
            part_num = 1
            
        start_idx = (part_num - 1) * chunk_size
        st_ids = all_students[start_idx : start_idx + chunk_size]
            
        t_id = entry.section.teacher_id
        req_cap = len(st_ids) # 100% capacity interleaving (no * 2)
        
        entry_data[entry.id] = {
            'teacher_id': t_id,
            'student_ids': st_ids,
            'req_cap': req_cap
        }
        
        teacher_slot_counts[(s_idx, t_id)] += 1
        venue_slot_usage[(s_idx, v_id)] += req_cap
        for stid in st_ids:
            student_slot_counts[(stid, s_idx)] += 1
            student_daily_slots[stid][s_idx // 4].append(s_idx) # 4 slots per day

    def calc_student_gap_pen(stid, day):
        slots = sorted(student_daily_slots[stid][day])
        pen = 0
        if len(slots) > 1:
            pen += (len(slots) - 1) * 20 # Soft base penalty for multiple exams a day
            for i in range(len(slots)-1):
                dist = slots[i+1] - slots[i]
                if dist == 1:
                    pen += 100 # Huge penalty for consecutive exams
                elif dist > 2:
                    pen += (dist - 2) * 50 # Heavy penalty for gap > 1 slot break
                # dist == 2 (exactly 1 slot break) adds 0 penalty!
        return pen

    def get_initial_penalties():
        t_pen = 0
        v_pen = 0
        s_pen = 0
        g_pen = 0
        
        for count in teacher_slot_counts.values():
            if count > 1: t_pen += (count - 1)
            
        for (s, v), occ in venue_slot_usage.items():
            if occ > venue_caps[v]: v_pen += (occ - venue_caps[v])
            
        for count in student_slot_counts.values():
            if count > 1: s_pen += (count - 1)
            
        for stid, daily in student_daily_slots.items():
            for day in daily:
                g_pen += calc_student_gap_pen(stid, day)
            
        return t_pen, v_pen, s_pen, g_pen

    curr_t, curr_v, curr_s, curr_g = get_initial_penalties()
    print(f"Initial State -> Teacher Clashes: {curr_t}, Venue Overflow: {curr_v}, Student Clashes: {curr_s}, Gaps: {curr_g}")
    
    if curr_t == 0 and curr_v == 0 and curr_s == 0 and curr_g == 0:
        print("Schedule is already perfect!")
        return

    # Simulated Annealing
    start_time = time.time()
    iterations = 0
    temp = 100.0
    cooling = 0.999995 # Very slow cooling
    
    best_chrom = chrom.copy()
    best_t, best_v, best_s, best_g = curr_t, curr_v, curr_s, curr_g
    
    entry_ids = list(chrom.keys())
    
    print("Starting Fast Optimization (Gaps & Clashes)...")
    while time.time() - start_time < 60 and temp > 0.01: # 1 minute max for SA (Total time = 5 mins)
        if best_t == 0 and best_v == 0 and best_s == 0 and best_g == 0:
            break # Perfect!
            
        eid = random.choice(entry_ids)
        old_s, old_v = chrom[eid]
        
        new_s = random.choice(slot_ids)
        new_v = random.choice(venues).id
        
        if old_s == new_s and old_v == new_v:
            continue
            
        data = entry_data[eid]
        t_id = data['teacher_id']
        st_ids = data['student_ids']
        req_cap = data['req_cap']
        
        # Calculate Delta
        delta_t = 0
        delta_v = 0
        delta_s = 0
        delta_g = 0
        
        # Remove old
        if teacher_slot_counts[(old_s, t_id)] > 1: delta_t -= 1
        
        old_v_occ = venue_slot_usage[(old_s, old_v)]
        if old_v_occ > venue_caps[old_v]:
            delta_v -= min(req_cap, old_v_occ - venue_caps[old_v])
            
        old_day = old_s // 4
        new_day = new_s // 4
        
        for stid in st_ids:
            if student_slot_counts[(stid, old_s)] > 1: delta_s -= 1
            
            # Gap delta (Old)
            old_g_before = calc_student_gap_pen(stid, old_day)
            student_daily_slots[stid][old_day].remove(old_s)
            old_g_after = calc_student_gap_pen(stid, old_day)
            delta_g += (old_g_after - old_g_before)
            
        # Add new
        if teacher_slot_counts[(new_s, t_id)] >= 1: delta_t += 1
        
        new_v_occ = venue_slot_usage[(new_s, new_v)]
        if new_v_occ + req_cap > venue_caps[new_v]:
            delta_v += min(req_cap, new_v_occ + req_cap - venue_caps[new_v])
            
        for stid in st_ids:
            if student_slot_counts[(stid, new_s)] >= 1: delta_s += 1
            
            # Gap delta (New)
            new_g_before = calc_student_gap_pen(stid, new_day)
            student_daily_slots[stid][new_day].append(new_s)
            new_g_after = calc_student_gap_pen(stid, new_day)
            delta_g += (new_g_after - new_g_before)
            
        # Evaluate: HUGE penalty for clashes, strong penalty for gaps
        cost_diff = (delta_t * 50000 + delta_v * 10 + delta_s * 10000 + delta_g * 1000)
        
        # Add penalty for Main Auditorium to deprioritize it
        if new_v == auditorium_id:
            cost_diff += 1 # Slight penalty
        if old_v == auditorium_id:
            cost_diff -= 1 # Slight reward for leaving
        
        if cost_diff < 0 or random.random() < 2.71828 ** (-cost_diff / temp):
            # Accept
            chrom[eid] = (new_s, new_v)
            curr_t += delta_t
            curr_v += delta_v
            curr_s += delta_s
            curr_g += delta_g
            
            teacher_slot_counts[(old_s, t_id)] -= 1
            teacher_slot_counts[(new_s, t_id)] += 1
            
            venue_slot_usage[(old_s, old_v)] -= req_cap
            venue_slot_usage[(new_s, new_v)] += req_cap
            
            for stid in st_ids:
                student_slot_counts[(stid, old_s)] -= 1
                student_slot_counts[(stid, new_s)] += 1
                # Daily slots already updated during delta calculation
                
            if (curr_t * 50000 + curr_v * 10 + curr_s * 10000 + curr_g * 1000) < (best_t * 50000 + best_v * 10 + best_s * 10000 + best_g * 1000):
                best_chrom = chrom.copy()
                best_t, best_v, best_s, best_g = curr_t, curr_v, curr_s, curr_g
        else:
            # Reject: Revert student_daily_slots
            for stid in st_ids:
                student_daily_slots[stid][old_day].append(old_s)
                student_daily_slots[stid][new_day].remove(new_s)
                
        iterations += 1
        temp *= cooling

    print(f"\nOptimization Finished in {time.time()-start_time:.1f}s after {iterations} iterations.")
    print(f"Final State -> Teacher Clashes: {best_t}, Venue Overflow: {best_v}, Student Clashes: {best_s}, Gaps: {best_g}")

    
    # Save back to DB
    print("Saving optimized schedule...")
    slot_objs = {s.slot_index: s for s in slots}
    venue_objs = {v.id: v for v in venues}
    
    for entry in entries:
        eid = entry.id
        s_idx, v_id = best_chrom[eid]
        entry.slot = slot_objs[s_idx]
        entry.venue = venue_objs[v_id]
        
    ScheduleEntry.objects.bulk_update(entries, ['slot', 'venue'])
    print("Saved successfully!")

if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else None
    fast_optimize(sid)
