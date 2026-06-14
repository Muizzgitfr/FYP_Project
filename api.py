import os
import django
import threading
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Initialize Django (allows us to read the DB if needed)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.models import ExamSchedule

app = FastAPI(title="Scheduler Engine API", description="Python Microservice for GA Scheduling")

# Allow Node.js backend to talk to us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to the Node.js server IP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Constraints(BaseModel):
    no_double_booking: bool = True
    prevent_faculty_clash: bool = True
    room_capacity_check: bool = True
    avoid_consecutive_classes: bool = False

class ScheduleParams(BaseModel):
    academic_session: str = "Fall 2026"
    department: str = "Computer Science"
    schedule_type: str = "Exam Timetable"
    start_time: str = "08:30"
    end_time: str = "16:30"
    slot_duration: str = "2 Hours"
    break_duration: str = "15 Minutes"
    constraints: Constraints = Constraints()

# Global State Tracker (In-Memory)
generation_state = {
    "is_running": False,
    "step": "Idle",
    "schedule_id": None,
    "error": None
}

def run_scheduling_pipeline():
    """Background thread that runs the heavy Python scripts sequentially."""
    global generation_state
    try:
        # Step 1: Run Genetic Algorithm
        generation_state["step"] = "Running Genetic Algorithm (Baseline Generation)..."
        result_ga = subprocess.run(["venv/bin/python3", "run_ga.py"], capture_output=True, text=True)
        if result_ga.returncode != 0:
            raise Exception(f"GA Failed: {result_ga.stderr}")

        # Get the ID of the newly generated schedule
        latest_schedule = ExamSchedule.objects.order_by('-created_at').first()
        if not latest_schedule:
            raise Exception("GA finished but no schedule was found in the database.")
        
        schedule_id = latest_schedule.id

        # Step 2: Run Fast Optimizer
        generation_state["step"] = "Running Simulated Annealing (Micro-Optimization)..."
        result_opt = subprocess.run(["venv/bin/python3", "fast_optimizer.py", str(schedule_id)], capture_output=True, text=True)
        if result_opt.returncode != 0:
            raise Exception(f"Optimizer Failed: {result_opt.stderr}")

        # Step 3: Fix Venues
        generation_state["step"] = "Running Venue Post-Processor (Capacity Fixing)..."
        result_venues = subprocess.run(["venv/bin/python3", "fix_venues.py"], capture_output=True, text=True)
        if result_venues.returncode != 0:
            raise Exception(f"Venue Fixer Failed: {result_venues.stderr}")

        # Finished Successfully!
        generation_state["step"] = "Completed"
        generation_state["schedule_id"] = schedule_id
        generation_state["is_running"] = False

    except Exception as e:
        generation_state["step"] = "Failed"
        generation_state["error"] = str(e)
        generation_state["is_running"] = False


@app.post("/api/generate-schedule")
def generate_schedule(params: ScheduleParams):
    """Endpoint triggered by Node.js to start the scheduling process."""
    global generation_state
    
    if generation_state["is_running"]:
        raise HTTPException(status_code=400, detail="A schedule generation is already in progress.")

    # Save incoming parameters to config json
    import json
    try:
        with open("params.json", "w") as f:
            json.dump(params.dict(), f, indent=2)
    except Exception as e:
        print(f"Error saving params: {e}")

    # Reset state
    generation_state["is_running"] = True
    generation_state["step"] = "Initializing..."
    generation_state["schedule_id"] = None
    generation_state["error"] = None

    # Spawn background thread
    thread = threading.Thread(target=run_scheduling_pipeline)
    thread.start()

    return {
        "status": "started",
        "message": "Scheduling engine has started processing in the background."
    }

@app.get("/api/schedule-status")
def schedule_status():
    """Endpoint polled by Node.js to check the progress of the scheduling process."""
    return generation_state

# --- PDF Generation Endpoints ---
import tempfile
from fastapi.responses import FileResponse
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

@app.get("/api/reports/schedule-pdf")
def get_schedule_pdf():
    from scheduler.models import ExamSchedule, ScheduleEntry
    latest_run = ExamSchedule.objects.order_by('-id').first()
    if not latest_run:
        raise HTTPException(status_code=404, detail="No schedule found")
        
    entries = list(ScheduleEntry.objects.filter(schedule=latest_run)\
                   .select_related('section__course', 'slot', 'venue', 'section__teacher')\
                   .order_by('section__course__code', 'section__name', 'part'))
                   
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    
    doc = SimpleDocTemplate(path, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph(f"Generated Exam Schedule (Schedule ID: {latest_run.id})", styles['Title']))
    elements.append(Spacer(1, 15))
    
    table_data = [["Course Code", "Course Name", "Section Part", "Date", "Time Slot", "Venue (Building)"]]
    for e in entries:
        table_data.append([
            e.section.course.code,
            e.section.course.name,
            f"{e.section.name} ({e.part})",
            str(e.slot.date),
            f"{e.slot.start_time.strftime('%H:%M')} - {e.slot.end_time.strftime('%H:%M')}",
            f"{e.venue.name} ({e.venue.building or 'Main Campus'})"
        ])
        
    t = Table(table_data, colWidths=[80, 200, 90, 80, 90, 150])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t)
    doc.build(elements)
    
    return FileResponse(path, media_type="application/pdf", filename="exam_schedule.pdf")

@app.get("/api/reports/students-pdf")
def get_students_pdf():
    from scheduler.models import ExamSchedule, ScheduleEntry, Enrollment
    latest_run = ExamSchedule.objects.order_by('-id').first()
    if not latest_run:
        raise HTTPException(status_code=404, detail="No schedule found")
        
    entries = list(ScheduleEntry.objects.filter(schedule=latest_run)\
                   .select_related('section__course', 'slot', 'venue', 'section__teacher')\
                   .order_by('section__course__code', 'section__name', 'part'))
                   
    # Pre-fetch all enrollments in a single query to eliminate N+1 loop lookup delays
    from collections import defaultdict
    enrollments_qs = Enrollment.objects.all().select_related('student__department').order_by('student_id')
    section_students = defaultdict(list)
    for enr in enrollments_qs:
        section_students[enr.section_id].append(enr)
        
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    
    doc = SimpleDocTemplate(path, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph(f"Course Student Lists & Venues (Schedule ID: {latest_run.id})", styles['Title']))
    elements.append(Spacer(1, 20))
    
    for entry in entries:
        elements.append(Paragraph(f"Course: {entry.section.course.name} ({entry.section.course.code})", styles['Heading2']))
        elements.append(Paragraph(f"Section: {entry.section.name} | Part: {entry.part}", styles['Normal']))
        elements.append(Paragraph(f"Venue: {entry.venue.name} ({entry.venue.building or 'Main Campus'}) | Slot Index: {entry.slot.slot_index}", styles['Normal']))
        elements.append(Paragraph(f"Date: {entry.slot.date} | Time: {entry.slot.start_time.strftime('%H:%M')} - {entry.slot.end_time.strftime('%H:%M')}", styles['Normal']))
        elements.append(Spacer(1, 10))
        
        all_enrs = section_students[entry.section_id]
        mid = len(all_enrs) // 2
        if entry.part == 'Part 1':
            assigned_students = all_enrs[:mid]
        else:
            assigned_students = all_enrs[mid:]
            
        table_data = [["Student ID", "Name", "Department", "Status"]]
        for enr in assigned_students:
            table_data.append([
                enr.student.student_id,
                enr.student.name,
                enr.student.department.name if enr.student.department else 'N/A',
                enr.student.status
            ])
            
        t = Table(table_data, colWidths=[100, 180, 150, 70])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 25))
        
    doc.build(elements)
    
    return FileResponse(path, media_type="application/pdf", filename="course_students_venue.pdf")
