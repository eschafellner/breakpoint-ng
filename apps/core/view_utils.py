from django.http import Http404


def positive_pk(value):
    """Malformed identifiers are a missing resource, never a server error."""
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise Http404 from exc
    if result <= 0 or result > 9223372036854775807:
        raise Http404
    return result
