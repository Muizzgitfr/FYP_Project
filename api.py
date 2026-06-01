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
def generate_schedule():
    """Endpoint triggered by Node.js to start the scheduling process."""
    global generation_state
    
    if generation_state["is_running"]:
        raise HTTPException(status_code=400, detail="A schedule generation is already in progress.")

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
