from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Exam, Question

import re

class UserRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'role')

    def clean(self):
        cleaned_data = super().clean()
        # In UserCreationForm, the field is slightly different, usually we just validate from self.cleaned_data if present, else self.data
        password = self.data.get('password1') or self.data.get('password')
        if not password: # If using custom template without predefined fields maybe? UserCreationForm usually uses password1.
            # But just in case
            pass
        elif password:
            errors = []
            if len(password) < 8:
                errors.append("Password must be at least 8 characters long.")
            if not any(char.isupper() for char in password):
                errors.append("Password must contain at least one uppercase letter.")
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
                errors.append("Password must contain at least one special character.")
            
            if errors:
                for error in errors:
                    self.add_error(None, error)
        return cleaned_data

class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ('title', 'description', 'date', 'duration', 'is_active')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ('text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option')
