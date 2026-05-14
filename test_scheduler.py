import random
from datetime import date, time as dtime
from collections import defaultdict
from scheduler.ga_enginee import GeneticAlgorithmScheduler

def test_model():
    print("🚀 Starting Model Test...")
    
    # 1. Mock Data (Small Dataset: 10 Courses)
    courses = [
        {'id': i, 'student_count': random.randint(20, 100)} for i in range(10)
    ]
    
    venues = [
        {'id': 101, 'capacity': 50},
        {'id': 102, 'capacity': 100},
        {'id': 103, 'capacity': 150},
    ]
    
    # 7 days, 2 slots per day
    slots = []
    for day in range(7):
        slots.append({'slot_index': day*2, 'date': date(2026, 5, 1+day), 'start_time': dtime(9, 0)})
        slots.append({'slot_index': day*2+1, 'date': date(2026, 5, 1+day), 'start_time': dtime(14, 0)})
        
    # Mock Conflict Matrix (some students share courses)
    conflict_matrix = defaultdict(int)
    # Course 0 and 1 share 10 students
    conflict_matrix[(0, 1)] = 10
    # Course 2 and 3 share 5 students
    conflict_matrix[(2, 3)] = 5
    
    # Mock Slot Distances
    distances = {}
    for s1 in slots:
        for s2 in slots:
            # Simple distance: 5 hours between slots on same day, 24 hours between days
            d1 = s1['slot_index'] // 2
            d2 = s2['slot_index'] // 2
            h1 = 9 if s1['slot_index'] % 2 == 0 else 14
            h2 = 9 if s2['slot_index'] % 2 == 0 else 14
            distances[(s1['slot_index'], s2['slot_index'])] = abs((d1 - d2) * 24 + (h1 - h2))

    # 2. Run Engine
    print("🧬 Running Genetic Algorithm...")
    engine = GeneticAlgorithmScheduler(
        courses, venues, slots, conflict_matrix, distances,
        population_size=20, generations=50
    )
    
    best_schedule, best_fitness = engine.run()
    
    # 3. Output Results
    print(f"\n✅ Optimization Complete!")
    print(f"Final Fitness: {best_fitness:.8f}")
    print("\nGenerated Schedule:")
    for c_id, (s_idx, v_id) in sorted(best_schedule.items()):
        slot = next(s for s in slots if s['slot_index'] == s_idx)
        print(f"Course {c_id:2} | Slot {s_idx:2} ({slot['date']} {slot['start_time']}) | Venue {v_id}")

if __name__ == "__main__":
    test_model()
