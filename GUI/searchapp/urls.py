from django.urls import path
from . import views

urlpatterns = [
    path("", views.search_home, name="search_home"),
    path("search/", views.search, name="search"),
    path("download/", views.start_download, name="start_download"),
    path("series-metadata/", views.series_metadata, name="series_metadata"),
]
