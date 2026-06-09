import os
import django
import pytest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.models import Section, Venue, ExamSlot, Student, Enrollment
from scheduler.ga_enginee import GeneticAlgorithmScheduler

@pytest.fixture
def dummy_data():
    return {
        'sections': [{'id': 1, 'teacher_id': 1}, {'id': 2, 'teacher_id': 2}],
        'venues': [{'id': 1, 'capacity': 50}, {'id': 2, 'capacity': 300}],
        'slots': [{'slot_index': 0, 'id': 1}],
        'distances': {(0, 0): 0},
    }

def test_session_chunking_20_limit(dummy_data):
    # Simulate a section with 75 students
    student_enrollments = {i: [1] for i in range(1, 76)} 
    
    engine = GeneticAlgorithmScheduler(
        sections=dummy_data['sections'], 
        venues=dummy_data['venues'], 
        slots=dummy_data['slots'], 
        student_enrollments=student_enrollments, 
        slot_distances=dummy_data['distances']
    )
    
    # Check that section 1 was split into exactly 4 chunks (20, 20, 20, 15)
    sessions = engine.sessions
    assert len(sessions) == 4
    assert sessions[0]['student_count'] == 20
    assert sessions[1]['student_count'] == 20
    assert sessions[2]['student_count'] == 20
    assert sessions[3]['student_count'] == 15
    assert sessions[0]['part'] == 'Part 1'
    assert sessions[3]['part'] == 'Part 4'

def test_capacity_interleaving(dummy_data):
    # Simulate 25 students in Sec 1, 25 students in Sec 2
    student_enrollments = {i: [1] for i in range(1, 26)}
    student_enrollments.update({i: [2] for i in range(26, 51)})
    
    engine = GeneticAlgorithmScheduler(
        sections=dummy_data['sections'], 
        venues=dummy_data['venues'], 
        slots=dummy_data['slots'], 
        student_enrollments=student_enrollments, 
        slot_distances=dummy_data['distances']
    )
    
    # Force both sessions into Slot 0, Venue 1 (capacity 50)
    chrom = {
        engine.sessions[0]['session_id']: (0, 1),
        engine.sessions[1]['session_id']: (0, 1)
    }
    
    # Verify fitness doesn't penalize capacity since 25+25 = 50 <= 50 (100% capacity interleaving)
    fitness = engine.fitness(chrom)
    assert fitness > 0 # Should be very high if no penalty

if __name__ == "__main__":
    pytest.main(["-v", "test_scheduler.py"])
