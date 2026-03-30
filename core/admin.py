from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Exam, Question, Result, Violation

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'is_staff')
    list_filter = ('role', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Role Info', {'fields': ('role',)}),
    )

class QuestionInline(admin.StackedInline):
    model = Question
    extra = 1

class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'teacher', 'created_at', 'is_active')
    inlines = [QuestionInline]

class ViolationAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'violation_type', 'timestamp')
    list_filter = ('exam', 'violation_type')

admin.site.register(User, CustomUserAdmin)
admin.site.register(Exam, ExamAdmin)
admin.site.register(Result)
admin.site.register(Violation, ViolationAdmin)
