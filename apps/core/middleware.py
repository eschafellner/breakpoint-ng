class RealIPMiddleware:
    """Extract real client IP behind reverse proxy / Cloudflare Tunnel."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
        if cf_ip:
            request.META["REMOTE_ADDR"] = cf_ip.strip()
        else:
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip = x_forwarded_for.split(",")[0].strip()
                request.META["REMOTE_ADDR"] = ip

        return self.get_response(request)
