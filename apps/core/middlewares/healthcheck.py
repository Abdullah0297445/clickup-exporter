from django.http.response import HttpResponse


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            return HttpResponse(status=200)
        response = self.get_response(request)
        return response
