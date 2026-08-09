from django.urls import path

from reduction import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sites/", views.site_list, name="site_list"),
    path("sites/new/", views.site_add, name="site_add"),
    path("sites/<str:name>/", views.site_detail, name="site_detail"),
    path("sites/<str:name>/edit/", views.site_edit, name="site_edit"),
    path("sites/<str:name>/delete/", views.site_delete, name="site_delete"),
]
