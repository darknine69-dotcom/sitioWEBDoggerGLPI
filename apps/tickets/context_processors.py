from django.conf import settings


def dogger_config(request):
    return {"DOGGER": settings.DOGGER}
