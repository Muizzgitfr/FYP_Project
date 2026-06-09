import os
import django
import pandas as pd
from collections import defaultdict
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scheduler.models import ExamSchedule, ScheduleEntry

def export_latest_schedule():
    latest_run = ExamSchedule.objects.order_by('-id').first()
    if not latest_run:
        print("No schedule found.")
        return

    print(f"Exporting Schedule ID: {latest_run.id}")
    entries = list(ScheduleEntry.objects.filter(schedule=latest_run).select_related('section__course', 'slot', 'venue', 'section__teacher').order_by('slot__date', 'slot__start_time', 'venue__name'))

    # Group by Day
    day_entries = defaultdict(list)
    for e in entries:
        day_entries[e.slot.date].append({
            "Date": str(e.slot.date),
            "Time": f"{e.slot.start_time.strftime('%H:%M')} - {e.slot.end_time.strftime('%H:%M')}",
            "Course": f"{e.section.course.code} - {e.section.course.name}",
            "Section Part": f"{e.section.name} ({e.part})",
            "Teacher": e.section.teacher.name,
            "Venue": e.venue.name,
            "Capacity": e.venue.capacity
        })

    # Export to Excel
    with pd.ExcelWriter(f'schedule_export_{latest_run.id}.xlsx') as writer:
        for date, rows in day_entries.items():
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name=str(date), index=False)
    print("✅ Excel export complete.")

    # Export to PDF
    pdf_filename = f'schedule_export_{latest_run.id}.pdf'
    doc = SimpleDocTemplate(pdf_filename, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph(f"Exam Schedule (ID: {latest_run.id})", styles['Title']))
    elements.append(Spacer(1, 12))

    for date in sorted(day_entries.keys()):
        elements.append(Paragraph(f"Date: {date}", styles['Heading2']))
        
        # Prepare table data
        table_data = [["Time", "Course", "Section Part", "Teacher", "Venue", "Capacity"]]
        for row in day_entries[date]:
            table_data.append([
                row["Time"], row["Course"], row["Section Part"], 
                row["Teacher"], row["Venue"], str(row["Capacity"])
            ])
            
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        elements.append(t)
        elements.append(Spacer(1, 24))

    doc.build(elements)
    print("✅ PDF export complete.")

if __name__ == "__main__":
    export_latest_schedule()
