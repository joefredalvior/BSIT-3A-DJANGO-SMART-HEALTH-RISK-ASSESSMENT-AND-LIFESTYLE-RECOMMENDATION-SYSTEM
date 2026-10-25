"""Small HTTP request helpers shared by middleware and error views."""


def wants_json(request):
    accept = request.headers.get('Accept', '')
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in accept
        or request.content_type == 'application/json'
    )
