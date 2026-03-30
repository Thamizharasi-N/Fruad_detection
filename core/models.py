from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')


class Exam(models.Model):
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'})
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField(null=True, blank=True, help_text='Scheduled exam date')
    duration = models.PositiveIntegerField(default=60, help_text='Duration in minutes')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class Question(models.Model):
    exam = models.ForeignKey(Exam, related_name='questions', on_delete=models.CASCADE)
    text = models.TextField()
    option_a = models.CharField(max_length=100)
    option_b = models.CharField(max_length=100)
    option_c = models.CharField(max_length=100)
    option_d = models.CharField(max_length=100)
    correct_option = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')])


class Result(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'student'})
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    score = models.IntegerField()
    total_questions = models.IntegerField(default=0)
    time_taken = models.CharField(max_length=50, default='0:00')
    violations_count = models.IntegerField(default=0)
    fraud_score = models.IntegerField(default=0)
    status = models.CharField(max_length=50, default='Completed')
    submitted_at = models.DateTimeField(auto_now_add=True)


# Mapping from violation type to structured dataset folder name
VIOLATION_FOLDER_MAP = {
    'Face Not Visible':       'face_not_visible',
    'Multiple Persons':       'multiple_face',
    'Looking Away':           'looking_away',
    'Book Detected':          'book_visible',
    'Mobile Phone Detected':  'mobile_phone',
    'Tab/Window Switched':    'normal',
    'Window Lost Focus':      'normal',
    'Noise Detected':         'normal',
}


def violation_directory_path(instance, filename):
    """Save snapshots into structured dataset/<violation_type>/ folders."""
    folder = VIOLATION_FOLDER_MAP.get(instance.violation_type, 'other')
    return f'dataset/{folder}/{filename}'


class Violation(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'student'})
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    violation_type = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    evidence = models.ImageField(upload_to=violation_directory_path, null=True, blank=True)
