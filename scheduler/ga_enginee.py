import random
import time
from datetime import datetime
from collections import defaultdict

class GeneticAlgorithmScheduler:
    def __init__(self, sections, venues, slots, student_enrollments, slot_distances, 
                 population_size=30, generations=60, mutation_rate=0.4, constraints=None):
        self.venues = venues
        self.venues_dict = {v['id']: v for v in venues}
        self.slots = slots
        self.slot_distances = slot_distances
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate

        # Initialize constraints
        if constraints is None:
            constraints = {}
        self.no_double_booking = constraints.get('no_double_booking', True)
        self.prevent_faculty_clash = constraints.get('prevent_faculty_clash', True)
        self.room_capacity_check = constraints.get('room_capacity_check', True)
        self.avoid_consecutive_classes = constraints.get('avoid_consecutive_classes', False)

        self.sessions = [] 
        self.student_to_sessions = defaultdict(list)
        
        for sec in sections:
            enrolled_students = [sid for sid, sids in student_enrollments.items() if sec['id'] in sids]
            
            # Chunk students into groups of max 20
            chunk_size = 20
            chunks = [enrolled_students[i:i + chunk_size] for i in range(0, len(enrolled_students), chunk_size)]
            
            for idx, chunk in enumerate(chunks):
                session_id = f"{sec['id']}_p{idx+1}"
                sess = {
                    'session_id': session_id,
                    'section_id': sec['id'],
                    'teacher_id': sec['teacher_id'],
                    'student_count': len(chunk),
                    'student_ids': chunk,
                    'part': f"Part {idx+1}"
                }
                self.sessions.append(sess)
                for sid in chunk: 
                    self.student_to_sessions[sid].append(session_id)

        self.sessions_dict = {s['session_id']: s for s in self.sessions}
        self.session_conflict_matrix = defaultdict(int)
        for sid, sess_list in self.student_to_sessions.items():
            for i in range(len(sess_list)):
                for j in range(i + 1, len(sess_list)):
                    pair = tuple(sorted((sess_list[i], sess_list[j])))
                    self.session_conflict_matrix[pair] += 1

    def random_chromosome(self):
        chromosome = {}
        # Initial random placement, repair will fix it
        for sess in self.sessions:
            chromosome[sess['session_id']] = (random.choice(self.slots)['slot_index'], random.choice(self.venues)['id'])
        return self.repair(chromosome)

    def repair(self, chromosome):
        """Optimized Repair: Focus ONLY on Hard Constraints (Zero Clashes)"""
        venue_slot_usage = defaultdict(int)
        venue_slot_sections = defaultdict(set)
        teacher_slot_usage = {}
        student_slot_usage = defaultdict(set)

        sess_ids = list(chromosome.keys())
        random.shuffle(sess_ids)

        for sid in sess_ids:
            sess = self.sessions_dict[sid]
            req_cap = sess['student_count']  # Interleaved courses, 100% physical capacity usage
            s_idx, v_id = chromosome[sid]
            
            # Conflict if: Capacity Overflow OR Teacher Busy OR Student Clash OR Venue Double Booked
            is_cap_overflow = False
            if self.room_capacity_check:
                is_cap_overflow = (venue_slot_usage[(s_idx, v_id)] + req_cap > self.venues_dict[v_id]['capacity'])

            is_double_booked = False
            if self.no_double_booking:
                if (s_idx, v_id) in venue_slot_sections and sess['section_id'] not in venue_slot_sections[(s_idx, v_id)]:
                    is_double_booked = True

            is_faculty_clash = False
            if self.prevent_faculty_clash:
                if (s_idx, sess['teacher_id']) in teacher_slot_usage:
                    is_faculty_clash = True

            is_student_clash = any(stid in student_slot_usage[s_idx] for stid in sess['student_ids'])

            has_conflict = is_cap_overflow or is_double_booked or is_faculty_clash or is_student_clash
            
            if has_conflict:
                found = False
                all_slots = list(range(len(self.slots)))
                random.shuffle(all_slots)
                
                for s_i in all_slots:
                    # 1. Check teacher clash (slot-specific)
                    if self.prevent_faculty_clash and (s_i, sess['teacher_id']) in teacher_slot_usage:
                        continue
                        
                    # 2. Check student clash (slot-specific)
                    if any(stid in student_slot_usage[s_i] for stid in sess['student_ids']):
                        continue
                        
                    # 3. Find eligible venues (avoiding slow nested list comprehensions)
                    eligible_venues = []
                    for v in self.venues:
                        v_id = v['id']
                        # Capacity check
                        if self.room_capacity_check and venue_slot_usage[(s_i, v_id)] + req_cap > v['capacity']:
                            continue
                        # Double booking check
                        if self.no_double_booking and (s_i, v_id) in venue_slot_sections and sess['section_id'] not in venue_slot_sections[(s_i, v_id)]:
                            continue
                        eligible_venues.append(v)
                        
                    if not eligible_venues:
                        continue
                        
                    # Deprioritize Main Auditorium
                    std_venues = [v for v in eligible_venues if v['name'] != 'Main Auditorium']
                    if std_venues:
                        chosen_v = random.choice(std_venues)
                    else:
                        chosen_v = random.choice(eligible_venues)
                        
                    chromosome[sid] = (s_i, chosen_v['id'])
                    s_idx, v_id = s_i, chosen_v['id']
                    found = True
                    break
            
            # Update maps
            venue_slot_usage[(s_idx, v_id)] += req_cap
            venue_slot_sections[(s_idx, v_id)].add(sess['section_id'])
            teacher_slot_usage[(s_idx, sess['teacher_id'])] = sid
            for stid in sess['student_ids']:
                student_slot_usage[s_idx].add(stid)
            
        return chromosome

    def fitness(self, chromosome):
        conflict_penalty = 0
        gap_penalty = 0
        capacity_penalty = 0
        teacher_penalty = 0

        venue_slot_occupancy = defaultdict(int)
        venue_slot_sections = defaultdict(set)
        teacher_slot_usage = defaultdict(int)
        student_schedules = defaultdict(lambda: defaultdict(list)) # sid -> day -> [slot_idx]

        for sid, (s_idx, v_id) in chromosome.items():
            sess = self.sessions_dict[sid]
            # Teacher
            teacher_slot_usage[(s_idx, sess['teacher_id'])] += 1
            if self.prevent_faculty_clash and teacher_slot_usage[(s_idx, sess['teacher_id'])] > 1:
                teacher_penalty += 500000
            # Venue
            venue_slot_occupancy[(s_idx, v_id)] += sess['student_count']
            venue_slot_sections[(s_idx, v_id)].add(sess['section_id'])
            # Student Track
            for stid in sess['student_ids']:
                student_schedules[stid][s_idx // 5].append(s_idx)

        # 1. Student Clashes and Gaps
        for stid, daily in student_schedules.items():
            for day, slots in daily.items():
                if len(slots) > 1:
                    gap_penalty += (len(slots) - 1) * 20000 # Soft penalty for multiple exams a day
                    slots.sort()
                    # Check for clashes
                    for i in range(len(slots)-1):
                        if slots[i] == slots[i+1]:
                            conflict_penalty += 200000
                        else:
                            dist = slots[i+1] - slots[i]
                            if dist == 1:
                                if self.avoid_consecutive_classes:
                                    gap_penalty += 100000 # Consecutive exams are highly penalized
                                else:
                                    gap_penalty += 20000
                            elif dist > 2:
                                gap_penalty += (dist - 2) * 50000 # Gap > 1 slot is penalized

        # 2. Capacity penalty
        if self.room_capacity_check:
            for (s, v), occ in venue_slot_occupancy.items():
                cap = self.venues_dict[v]['capacity']
                if occ > cap: capacity_penalty += (occ - cap) * 2000

        # 3. Double booking penalty
        if self.no_double_booking:
            for (s, v), sects in venue_slot_sections.items():
                if len(sects) > 1:
                    conflict_penalty += (len(sects) - 1) * 100000

        total = conflict_penalty + gap_penalty + capacity_penalty + teacher_penalty
        return 1 / (1 + total)

    def run(self):
        start_time = time.time()
        population = [self.random_chromosome() for _ in range(self.population_size)]
        best_overall = None
        best_fitness_overall = -1

        for gen in range(self.generations):
            fitnesses = [self.fitness(c) for c in population]
            idx = fitnesses.index(max(fitnesses))
            if fitnesses[idx] > best_fitness_overall:
                best_fitness_overall = fitnesses[idx]
                best_overall = population[idx].copy()
                print(f"Gen {gen}: Fitness = {best_fitness_overall:.10f}")

            if (time.time() - start_time) > 240: break # 4 min limit for GA

            new_population = []
            # Elitism
            new_population.append(best_overall)
            
            while len(new_population) < self.population_size:
                p1 = self.select(population, fitnesses)
                p2 = self.select(population, fitnesses)
                child = self.repair(self.mutate(self.crossover(p1, p2)))
                new_population.append(child)
            population = new_population

        return best_overall, best_fitness_overall

    def select(self, pop, fits):
        tournament = random.sample(list(zip(pop, fits)), k=3)
        return max(tournament, key=lambda x: x[1])[0]

    def crossover(self, p1, p2):
        child = {}
        for sid in p1:
            child[sid] = p1[sid] if random.random() < 0.5 else p2[sid]
        return child

    def mutate(self, chromosome):
        for sid in chromosome:
            if random.random() < self.mutation_rate:
                if random.random() < 0.5:
                    chromosome[sid] = (random.choice(self.slots)['slot_index'], chromosome[sid][1])
                else:
                    chromosome[sid] = (chromosome[sid][0], random.choice(self.venues)['id'])
        return chromosome

def run_scheduler_django():
    from .models import Section, Venue, ExamSlot, Student, Enrollment
    from django.db.models import Count
    import json
    import os
    
    # Load parameters from params.json if it exists
    params = {}
    params_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'params.json')
    if os.path.exists(params_path):
        try:
            with open(params_path, 'r') as f:
                params = json.load(f)
        except Exception as e:
            print(f"⚠️ Error reading params.json: {e}")
            
    academic_session = params.get('academic_session', 'Fall 2026')
    department = params.get('department', '')
    schedule_type = params.get('schedule_type', 'Exam Timetable')
    start_time = params.get('start_time', '08:30')
    end_time = params.get('end_time', '16:30')
    constraints = params.get('constraints', {})
    
    print(f"📊 Filtering sections and slots based on parameters:")
    print(f"   - Session: {academic_session}")
    print(f"   - Department: {department}")
    print(f"   - Type: {schedule_type}")
    print(f"   - Time Window: {start_time} to {end_time}")
    
    # Filter sections by department
    sections_qs = Section.objects.all()
    if department:
        sections_filtered = sections_qs.filter(course__department__name__icontains=department)
        if sections_filtered.exists():
            sections_qs = sections_filtered
            print(f"   -> Filtered to {sections_qs.count()} sections for department: {department}")
        else:
            print(f"   -> No sections found for department: {department}. Falling back to all.")
            
    sections = list(sections_qs.annotate(student_count=Count('enrollments')).values('id', 'teacher_id', 'student_count'))
    venues = list(Venue.objects.all().values('id', 'capacity', 'name'))
    slots_raw = list(ExamSlot.objects.all().order_by('slot_index'))
    slots = [{'slot_index': s.slot_index, 'id': s.id, 'date': s.date, 'start_time': s.start_time} for s in slots_raw]
    
    student_enrollments = defaultdict(list)
    enrollments = Enrollment.objects.all().values('student_id', 'section_id')
    for e in enrollments:
        student_enrollments[e['student_id']].append(e['section_id'])
                
    distances = {}
    for s1 in slots:
        for s2 in slots:
            dt1 = datetime.combine(s1['date'], s1['start_time'])
            dt2 = datetime.combine(s2['date'], s2['start_time'])
            distances[(s1['slot_index'], s2['slot_index'])] = abs((dt1 - dt2).total_seconds() / 3600.0)
            
    engine = GeneticAlgorithmScheduler(sections, venues, slots, student_enrollments, distances, constraints=constraints)
    best_schedule, fitness = engine.run()
    return best_schedule, fitness, engine.sessions_dict