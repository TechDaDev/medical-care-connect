from django.urls import path

from apps.privacy import views

app_name = "privacy"

urlpatterns = [
    # Data export
    path("exports/", views.export_list_create, name="export-list-create"),
    path("exports/<uuid:id>/", views.export_detail, name="export-detail"),
    path("exports/<uuid:id>/download/", views.export_download, name="export-download"),
    # Account
    path("account/deactivate/", views.deactivate_account, name="account-deactivate"),
    path("account/reactivate/", views.reactivate_account, name="account-reactivate"),
    # Deletion
    path("deletion-requests/", views.deletion_list_create, name="deletion-list-create"),
    path("deletion-requests/<uuid:id>/", views.deletion_detail_cancel, name="deletion-detail-cancel"),
    path(
        "deletion-requests/<uuid:id>/cancel/",
        views.deletion_detail_cancel,
        name="deletion-cancel",
    ),
]
