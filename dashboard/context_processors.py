from django.core.cache import cache


def sidebar_devices(request):
    """Inject cached device list into every template context.

    Reads from the shared cache key populated by _get_cached_devices().
    Returns empty dict on cache miss – template falls back to HTMX lazy-load.
    """
    devices = cache.get('devices:shared:v1')
    if devices and isinstance(devices, list) and all(isinstance(d, dict) for d in devices):
        return {'sidebar_devices': devices}
    return {}
