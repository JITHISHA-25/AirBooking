from rest_framework.exceptions import APIException


class PaymentDeclined(APIException):
    status_code = 402
    default_detail = "The simulated payment was declined. No seats were reserved."


def simulate_payment(outcome, *, food_only=False):
    if outcome == "decline":
        if food_only:
            raise PaymentDeclined("The simulated food payment was declined. Your trip remains active; no food was ordered.")
        raise PaymentDeclined()
