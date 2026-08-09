from django.urls import path

from reduction import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sites/", views.site_list, name="site_list"),
    path("sites/new/", views.site_add, name="site_add"),
    path("sites/<str:name>/", views.site_detail, name="site_detail"),
    path("sites/<str:name>/edit/", views.site_edit, name="site_edit"),
    path("sites/<str:name>/delete/", views.site_delete, name="site_delete"),
    path("pipelines/", views.pipeline_list, name="pipeline_list"),
    path("pipelines/new/", views.pipeline_add, name="pipeline_add"),
    path("pipelines/<str:name>/", views.pipeline_detail, name="pipeline_detail"),
    path("pipelines/<str:name>/edit/", views.pipeline_edit, name="pipeline_edit"),
    path("pipelines/<str:name>/delete/", views.pipeline_delete, name="pipeline_delete"),
    path("pipelines/<str:name>/steps/add/", views.pipeline_step_add, name="pipeline_step_add"),
    path("pipelines/<str:name>/steps/reorder/", views.pipeline_step_reorder, name="pipeline_step_reorder"),
    path("pipelines/<str:name>/steps/<int:step_id>/config/", views.pipeline_step_config, name="pipeline_step_config"),
    path("pipelines/<str:name>/steps/<int:step_id>/delete/", views.pipeline_step_delete, name="pipeline_step_delete"),
]
