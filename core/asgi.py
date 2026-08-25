"""
ASGI config for core project.

Routes plain HTTP to Django's normal view layer, and WebSocket connections
(the /ws/matchmaking/ endpoint) to Channels, authenticated via JWT.
"""
import os

import django
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from matching.middleware import JWTAuthMiddleware  # noqa: E402
from matching.routing import websocket_urlpatterns  # noqa: E402

# Note: this API targets native/mobile clients (an audio-chat app), which
# don't send a browser-style Origin header on WebSocket handshakes, so
# AllowedHostsOriginValidator (designed for browser CSRF-style protection)
# is intentionally not used here. Authentication instead happens per-message
# via the JWT in JWTAuthMiddleware; a browser-facing deployment would add
# CORS/Origin checks at the reverse-proxy layer instead.
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
})
