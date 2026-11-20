from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("booking", "0004_booking_cancellation_reason")]

    operations = [
        migrations.CreateModel(
            name="PickupShare",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pickup_shares", to="booking.booking")),
            ],
            options={"constraints": [models.UniqueConstraint(condition=models.Q(revoked_at__isnull=True),
                        fields=("booking",), name="one_unrevoked_pickup_share")]},
        ),
    ]
