from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views
from .food import AdminMeals, AdminFlightMeals, AdminFlightFood, BookingFood, CancelFood, FlightMenu

router = SimpleRouter()
router.register("bookings", views.Bookings, basename="bookings")
router.register("complaints", views.Complaints, basename="complaints")
router.register("admin/complaints", views.AdminComplaints, basename="admin-complaints")
router.register("admin/users", views.AdminUsers, basename="admin-users")
router.register("admin/flights", views.AdminFlights, basename="admin-flights")
router.register("admin/meals", AdminMeals, basename="admin-meals")

urlpatterns = [
    path("flights/<int:pk>/meals/", FlightMenu.as_view()),
    path("bookings/<int:pk>/food-orders/", BookingFood.as_view()),
    path("bookings/<int:pk>/food-orders/<int:order_id>/cancel/", CancelFood.as_view()),
    path("admin/flights/<int:pk>/meals/", AdminFlightMeals.as_view()),
    path("admin/flights/<int:pk>/food-orders/", AdminFlightFood.as_view()),
    path("auth/register/", views.Register.as_view()),
    path("auth/login/", views.Login.as_view()),
    path("auth/token/refresh/", views.Refresh.as_view()),
    path("auth/me/", views.Me.as_view()),
    path("auth/logout/", views.Logout.as_view()),
    path("flights/search/", views.FlightSearch.as_view()),
    path("flights/status/search/", views.FlightStatusSearch.as_view()),
    path("flights/<int:pk>/", views.FlightDetail.as_view()),
    path("flights/<int:pk>/status/", views.FlightLive.as_view()),
    path("admin/stats/", views.AdminStats.as_view()),
    path("", include(router.urls)),
]
