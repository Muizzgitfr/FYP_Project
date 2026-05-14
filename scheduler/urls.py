from django.urls import path
from . import views

urlpatterns = [
    path('student-schedule/', views.student_schedule, name='student_schedule'),
    path('gap-report/', views.gap_report, name='gap_report'),
]
