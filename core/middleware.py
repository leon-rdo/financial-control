class HTMXMiddleware:
    """
    Middleware to detect HTMX requests and add htmx attribute to request object
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.htmx = "HX-Request" in request.headers
        response = self.get_response(request)
        return response
