from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

PUBLIC_PREFIXES = ("/login", "/auth/", "/static/", "/setup")


class RequireLoginMiddleware(BaseHTTPMiddleware):
    """Everything except the login flow needs a session, so routes never check auth themselves."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(PUBLIC_PREFIXES) or request.session.get("email"):
            return await call_next(request)
        return RedirectResponse("/login", status_code=303)


def current_user(request: Request) -> dict:
    return {"email": request.session.get("email", ""), "name": request.session.get("name", "")}
