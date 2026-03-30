import cv2
import numpy as np
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import User, Exam, Result, Violation, Question
from .forms import UserRegistrationForm, ExamForm, QuestionForm
import base64
from django.core.files.base import ContentFile
from .detect import detect_violations_logic
import django.utils.timezone as timezone
from datetime import timedelta
import traceback

# --- Helper Checks ---
def is_teacher(user):
    return user.role == 'teacher'

def is_student(user):
    return user.role == 'student'

# --- Auth Views ---
def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserRegistrationForm()
    return render(request, 'register.html', {'form': form})

from django.views.decorators.csrf import csrf_protect

@csrf_protect
def student_login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.role != 'student':
                form.add_error(None, "This portal is for students. Please use Staff Login.")
            else:
                login(request, user)
                return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form, 'login_type': 'student'})

@csrf_protect
def staff_login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.role not in ['teacher', 'admin']:
                form.add_error(None, "This portal is for staff. Please use Student Login.")
            else:
                login(request, user)
                return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form, 'login_type': 'staff'})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard_view(request):
    if request.user.role == 'admin':
        return redirect('/admin/') # Or a custom admin dashboard
    elif request.user.role == 'teacher':
        exams = Exam.objects.filter(teacher=request.user)
        total_exams = exams.count()
        active_exams = exams.filter(is_active=True).count()
        total_students = User.objects.filter(role='student').count()
        total_violations = Violation.objects.filter(exam__in=exams).count()
        context = {
            'exams': exams,
            'total_exams': total_exams,
            'active_exams': active_exams,
            'total_students': total_students,
            'total_violations': total_violations
        }
        return render(request, 'teacher_dashboard.html', context)
    else: # Student
        exams = Exam.objects.filter(is_active=True)
        results = Result.objects.filter(student=request.user)
        return render(request, 'student_dashboard.html', {'exams': exams, 'results': results})

# --- Teacher Views ---
@login_required
@user_passes_test(is_teacher)
def create_exam_view(request):
    if request.method == 'POST':
        form = ExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.teacher = request.user
            exam.save()
            return redirect('dashboard')
    else:
        form = ExamForm()
    return render(request, 'create_exam.html', {'form': form})

@login_required
@user_passes_test(is_teacher)
def add_question_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.exam = exam
            question.save()
            return redirect('add_question', exam_id=exam.id)
    else:
        form = QuestionForm()
    questions = exam.questions.all()
    return render(request, 'add_question.html', {'form': form, 'exam': exam, 'questions': questions})

@login_required
@user_passes_test(is_teacher)
def view_results(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    results = Result.objects.filter(exam=exam)
    violations = Violation.objects.filter(exam=exam)
    return render(request, 'exam_results.html', {'exam': exam, 'results': results, 'violations': violations})

@login_required
@user_passes_test(is_teacher)
def view_all_reports(request):
    """Show consolidated reports for all exams created by this teacher."""
    exams = Exam.objects.filter(teacher=request.user)
    results = Result.objects.filter(exam__in=exams).select_related('student', 'exam').order_by('-submitted_at')
    return render(request, 'all_reports.html', {'results': results})

@login_required
@user_passes_test(is_teacher)
def edit_exam_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    if request.method == 'POST':
        form = ExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = ExamForm(instance=exam)
    return render(request, 'edit_exam.html', {'form': form, 'exam': exam})

@login_required
@user_passes_test(is_teacher)
def delete_exam_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    if request.method == 'POST':
        exam.delete()  # Cascades to Questions, Results, Violations
        return redirect('dashboard')
    return render(request, 'confirm_delete_exam.html', {'exam': exam})

# --- Student Views ---
@login_required
@user_passes_test(is_student)
def take_exam_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    # Check if already taken
    if Result.objects.filter(student=request.user, exam=exam).exists():
        return redirect('dashboard')
    
    questions = exam.questions.all()
    if request.method == 'POST':
        score = 0
        total_qs = questions.count()
        for q in questions:
            selected = request.POST.get(f'q_{q.id}')
            if selected == q.correct_option:
                score += 1
        
        time_taken = request.POST.get('time_taken', '0:00')
        
        # Process violations and fraud score
        violations_count = Violation.objects.filter(student=request.user, exam=exam).count()
        fraud_score = min(100, violations_count * 20)
        status = 'Terminated' if violations_count >= 3 else 'Completed'

        # Optional: check if terminated by JS
        if request.POST.get('status') == 'terminated':
            status = 'Terminated'

        Result.objects.create(
            student=request.user, 
            exam=exam, 
            score=score,
            total_questions=total_qs,
            time_taken=time_taken,
            violations_count=violations_count,
            fraud_score=fraud_score,
            status=status
        )
        return redirect('dashboard')

    return render(request, 'exam_portal.html', {'exam': exam, 'questions': questions})

# --- YOLO Detection Placeholder (Actual implementation in ml/detect.py) ---
# We will receive frames via AJAX POST for simplicity and robustness in basic server
@csrf_exempt
@login_required
def process_frame(request):
    if request.method == 'POST':
        image_data = request.POST.get('image')
        if image_data:
            try:
                # Decode image
                format, imgstr = image_data.split(';base64,') 
                ext = format.split('/')[-1]
                data = base64.b64decode(imgstr)
                
                # Convert to numpy for OpenCV
                nparr = np.frombuffer(data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                # Run Detection
                exam_id = request.POST.get('exam_id')
                if exam_id:
                    exam = get_object_or_404(Exam, id=exam_id)
                else:
                    exam = Exam.objects.filter(is_active=True).first()
                
                detection_result = detect_violations_logic(img, request.user, exam)
                
                # Get current violation count
                violation_count = Violation.objects.filter(student=request.user, exam=exam).count()
                
                if detection_result['status'] == 'violation':
                    # Throttling: Check if a violation was recorded in the last 5 seconds
                    last_violation = Violation.objects.filter(student=request.user, exam=exam).order_by('-timestamp').first()
                    
                    if not last_violation or (timezone.now() - last_violation.timestamp) > timedelta(seconds=5):
                        if exam:
                            violation_type_str = detection_result['violation_type']
                            v = Violation(
                                student=request.user,
                                exam=exam,
                                violation_type=violation_type_str
                            )
                            # Save image evidence via Django storage (structured by violation_directory_path)
                            file_name = f"{request.user.id}_{int(timezone.now().timestamp())}.{ext}"
                            v.evidence.save(file_name, ContentFile(data), save=True)
                            violation_count += 1
                            
                            # Also write a copy directly to dataset folder for CNN training
                            import os
                            from django.conf import settings as django_settings
                            from .models import VIOLATION_FOLDER_MAP
                            folder_name = VIOLATION_FOLDER_MAP.get(violation_type_str, 'other')
                            dataset_dir = os.path.join(django_settings.MEDIA_ROOT, 'dataset', folder_name)
                            os.makedirs(dataset_dir, exist_ok=True)
                            dataset_path = os.path.join(dataset_dir, file_name)
                            with open(dataset_path, 'wb') as f:
                                f.write(data)
                    
                termination_status = violation_count >= 3
                
                response_data = {
                    'status': detection_result['status'],
                    'violation_type': detection_result.get('violation_type'),
                    'violation_count': violation_count,
                    'terminated': termination_status
                }
                
                return JsonResponse(response_data)
            
            except Exception as e:
                print(f"Error processing frame: {e}")
                import traceback
                traceback.print_exc()
                return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error'})

@csrf_exempt
@login_required
def report_violation(request):
    if request.method == 'POST':
        violation_type = request.POST.get('violation_type')
        exam_id = request.POST.get('exam_id')
        exam = get_object_or_404(Exam, id=exam_id)
        
        # Throttling non-webcam violations (e.g. Tab Switching)
        last_violation = Violation.objects.filter(student=request.user, exam=exam, violation_type=violation_type).order_by('-timestamp').first()
        if not last_violation or (timezone.now() - last_violation.timestamp) > timedelta(seconds=10):
            v = Violation.objects.create(
                student=request.user,
                exam=exam,
                violation_type=violation_type
            )
        
        violation_count = Violation.objects.filter(student=request.user, exam=exam).count()
        termination_status = violation_count >= 3
        
        return JsonResponse({
            'status': 'success', 
            'violation_type': violation_type,
            'violation_count': violation_count,
            'terminated': termination_status
        })
    
    return JsonResponse({'status': 'error'})
