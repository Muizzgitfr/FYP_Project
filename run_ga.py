import os
import django
import time

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.ga_enginee import run_scheduler_django
from scheduler.models import ExamSchedule, ScheduleEntry, Course, Venue, ExamSlot

def main():
    print("🚀 Starting Genetic Algorithm Scheduler...")
    print(f"📊 Dataset Stats:")
    print(f"   - Students: {django.apps.apps.get_model('scheduler', 'Student').objects.count()}")
    print(f"   - Courses: {Course.objects.count()}")
    print(f"   - Enrollments: {django.apps.apps.get_model('scheduler', 'Enrollment').objects.count()}")
    print(f"   - Venues: {Venue.objects.count()}")
    print(f"   - Slots: {ExamSlot.objects.count()}")
    
    start_time = time.time()
    best_schedule, fitness, sessions_dict = run_scheduler_django()
    end_time = time.time()
    
    print(f"\n✅ Optimization Complete in {end_time - start_time:.2f} seconds!")
    print(f"🏆 Best Fitness: {fitness:.8f}")
    
    if best_schedule:
        print("\n💾 Saving Schedule to Database...")
        # Optimization: Pre-fetch slots to avoid 2800+ queries
        slots_map = {s.slot_index: s for s in ExamSlot.objects.all()}
        
        # Save to DB
        new_schedule = ExamSchedule.objects.create(
            name=f"Optimization Result {time.strftime('%Y-%m-%d %H:%M')}",
            fitness_score=fitness,
            is_active=True
        )
        
        entries = []
        for sess_id, (s_idx, v_id) in best_schedule.items():
            session_info = sessions_dict[sess_id]
            entries.append(ScheduleEntry(
                schedule=new_schedule,
                section_id=session_info['section_id'],
                slot=slots_map[s_idx],
                venue_id=v_id,
                part=session_info['part']
            ))
        ScheduleEntry.objects.bulk_create(entries)
        print(f"✨ Saved {len(entries)} entries to ExamSchedule ID: {new_schedule.id}")
    else:
        print("❌ No schedule was generated.")

if __name__ == "__main__":
    main()
