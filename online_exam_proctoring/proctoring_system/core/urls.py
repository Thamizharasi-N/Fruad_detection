from django.urls import path
from django.shortcuts import redirect
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', lambda request: redirect('student_login'), name='home'),
    path('register/', views.register_view, name='register'),
    path('student/login/', views.student_login_view, name='student_login'),
    path('staff/login/', views.staff_login_view, name='staff_login'),
    path('login/', lambda request: redirect('student_login'), name='login'), # Keep for login_required decorators
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Teacher
    path('exam/create/', views.create_exam_view, name='create_exam'),
    path('exam/<int:exam_id>/add_question/', views.add_question_view, name='add_question'),
    path('exam/<int:exam_id>/results/', views.view_results, name='view_results'),
    path('exam/<int:exam_id>/edit/', views.edit_exam_view, name='edit_exam'),
    path('exam/<int:exam_id>/delete/', views.delete_exam_view, name='delete_exam'),
    path('reports/', views.view_all_reports, name='all_reports'),
    
    # Student
    path('exam/<int:exam_id>/take/', views.take_exam_view, name='take_exam'),
    path('detect/', views.process_frame, name='process_frame'),
    path('report_violation/', views.report_violation, name='report_violation'),
    
    # Password Reset
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
]
