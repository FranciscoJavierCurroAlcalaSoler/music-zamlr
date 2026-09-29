import secrets

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

TOKEN_HEADER = "X-Zamlr-Token"


class TokenMiddleware:
    def __init__(self, app, secret: str) -> None:
        self.app = app
        self.secret = secret

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        value = Headers(scope=scope).get(TOKEN_HEADER)
        if value is None or not secrets.compare_digest(
            value.encode(), self.secret.encode()
        ):
            response = JSONResponse(
                {"detail": "Invalid or missing token"}, status_code=401
            )
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)
