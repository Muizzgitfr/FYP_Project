import random
import time
from datetime import datetime
from collections import defaultdict

class GeneticAlgorithmScheduler:
    def __init__(self, sections, venues, slots, student_enrollments, slot_distances, 
                 population_size=100, generations=500, mutation_rate=0.4):
        self.venues = venues
        self.venues_dict = {v['id']: v for v in venues}
        self.slots = slots
        self.slot_distances = slot_distances
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate

        self.sessions = [] 
        self.student_to_sessions = defaultdict(list)
        
        for sec in sections:
            enrolled_students = [sid for sid, sids in student_enrollments.items() if sec['id'] in sids]
            mid = len(enrolled_students) // 2
            p1_students = enrolled_students[:mid] # first 25
            p2_students = enrolled_students[mid:] # second 25
            
            #forr creating sessions
            s1 = {'session_id': f"{sec['id']}_p1", 'section_id': sec['id'], 'teacher_id': sec['teacher_id'], 'student_count': len(p1_students), 'student_ids': p1_students, 'part': 'Part 1'}
            s2 = {'session_id': f"{sec['id']}_p2", 'section_id': sec['id'], 'teacher_id': sec['teacher_id'], 'student_count': len(p2_students), 'student_ids': p2_students, 'part': 'Part 2'}
            
            self.sessions.extend([s1, s2])
            for sid in p1_students: self.student_to_sessions[sid].append(s1['session_id'])
            for sid in p2_students: self.student_to_sessions[sid].append(s2['session_id'])

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
        teacher_slot_usage = {}
        student_slot_usage = defaultdict(set)

        sess_ids = list(chromosome.keys())
        random.shuffle(sess_ids)

        for sid in sess_ids:
            sess = self.sessions_dict[sid]
            req_cap = sess['student_count'] * 2
            s_idx, v_id = chromosome[sid]
            
            # Conflict if: Capacity Overflow OR Teacher Busy OR Student Clash
            has_conflict = (venue_slot_usage[(s_idx, v_id)] + req_cap > self.venues_dict[v_id]['capacity']) or \
                           (s_idx, sess['teacher_id']) in teacher_slot_usage or \
                           any(stid in student_slot_usage[s_idx] for stid in sess['student_ids'])
            
            if has_conflict:
                found = False
                all_slots = list(range(len(self.slots)))
                random.shuffle(all_slots)
                
                for s_i in all_slots:
                    eligible_venues = [v for v in self.venues if venue_slot_usage[(s_i, v['id'])] + req_cap <= v['capacity']]
                    if not eligible_venues: continue
                    
                    if (s_i, sess['teacher_id']) not in teacher_slot_usage and \
                       not any(stid in student_slot_usage[s_i] for stid in sess['student_ids']):
                        chromosome[sid] = (s_i, random.choice(eligible_venues)['id'])
                        s_idx, v_id = chromosome[sid]
                        found = True
                        break
            
            # Update maps
            venue_slot_usage[(s_idx, v_id)] += req_cap
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
        teacher_slot_usage = defaultdict(int)
        student_schedules = defaultdict(lambda: defaultdict(list)) # sid -> day -> [slot_idx]

        for sid, (s_idx, v_id) in chromosome.items():
            sess = self.sessions_dict[sid]
            # Teacher
            teacher_slot_usage[(s_idx, sess['teacher_id'])] += 1
            if teacher_slot_usage[(s_idx, sess['teacher_id'])] > 1: teacher_penalty += 500000
            # Venue
            venue_slot_occupancy[(s_idx, v_id)] += sess['student_count'] * 2
            # Student Track
            for stid in sess['student_ids']:
                student_schedules[stid][s_idx // 5].append(s_idx)

        # 1. Student Clashes and Gaps
        for stid, daily in student_schedules.items():
            for day, slots in daily.items():
                if len(slots) > 1:
                    slots.sort()
                    # Check for clashes
                    for i in range(len(slots)-1):
                        if slots[i] == slots[i+1]:
                            conflict_penalty += 200000
                        else:
                            # Gap penalty: If more than 1 slot apart on same day
                            # Slot indices are 0,1,2,3,4 for each day.
                            # dist = 1 means consecutive. dist > 1 means a gap > 30 mins.
                            dist = slots[i+1] - slots[i]
                            if dist > 1:
                                gap_penalty += (dist - 1) * 100000 # Huge penalty for gaps!

        for (s, v), occ in venue_slot_occupancy.items():
            cap = self.venues_dict[v]['capacity']
            if occ > cap: capacity_penalty += (occ - cap) * 2000

        total = conflict_penalty + gap_penalty + capacity_penalty + teacher_penalty
        return 1 / (1 + total)

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

            if (time.time() - start_time) > 600: break # 10 min limit

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
    
    sections = list(Section.objects.annotate(student_count=Count('enrollments')).values('id', 'teacher_id', 'student_count'))
    venues = list(Venue.objects.all().values('id', 'capacity'))
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
            
    engine = GeneticAlgorithmScheduler(sections, venues, slots, student_enrollments, distances)
    best_schedule, fitness = engine.run()
    return best_schedule, fitness, engine.sessions_dict