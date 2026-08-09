from django.urls import path

from reduction import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
