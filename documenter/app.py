import secrets
import time
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from documenter import db, google_oauth, invite, local_state, repo, sync
from documenter.auth import RequireLoginMiddleware, current_user
from documenter.config import settings
from documenter.drive import DriveStorage
from documenter.models import LANGUAGES, DocumentFilter, DocumentInput
from documenter.storage import LocalStorage

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_access_token = {"value": "", "expires": 0.0}


def _drive_access_token() -> str:
    # Google access tokens live an hour; refreshing every 50 minutes keeps it simple and safe.
    if _access_token["expires"] < time.monotonic():
        refresh_token = local_state.load().get("drive_refresh_token")
        if not refresh_token:
            raise RuntimeError("Владелец ещё ни разу не входил, токен Drive не получен")
        _access_token["value"] = google_oauth.fetch_access_token(
            settings.google_client_id, settings.google_client_secret, refresh_token
        )
        _access_token["expires"] = time.monotonic() + 3000
    return _access_token["value"]


storage = (
    DriveStorage(_drive_access_token, settings.drive_folder_name)
    if settings.storage == "drive"
    else LocalStorage(settings.local_files_dir)
)

# The index in Drive is the real one; the file on this machine is a working copy of it.
# One message at a time is enough for an app used by one person at one computer.
notice = {"text": ""}
if settings.storage == "drive" and local_state.load().get("drive_refresh_token"):
    notice["text"] = sync.pull(storage, settings.db_path)

conn = db.connect(settings.db_path)
db.init_db(conn)

app = FastAPI()
app.add_middleware(RequireLoginMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates.env.globals["notice"] = lambda: notice["text"]
templates.env.globals["owner_email"] = settings.owner_email


SYNC_FREE_PREFIXES = ("/static", "/files", "/auth", "/login", "/setup", "/invite")
INDEX_CHECK_INTERVAL = 15.0
_last_index_check = {"at": 0.0}


def _time_to_check_drive(request: Request) -> bool:
    if settings.storage != "drive" or request.url.path.startswith(SYNC_FREE_PREFIXES):
        return False
    # Asking Drive costs a quarter of a second, which is too much on every click —
    # but a save must never land on top of a stale index, so writes always check.
    if request.method != "POST" and time.monotonic() - _last_index_check["at"] < INDEX_CHECK_INTERVAL:
        return False
    _last_index_check["at"] = time.monotonic()
    return True


@app.middleware("http")
async def keep_index_in_step_with_drive(request: Request, call_next):
    if _time_to_check_drive(request):
        notice["text"] = sync.refresh(conn, storage)
    response = await call_next(request)
    if request.method == "POST" and settings.storage == "drive":
        notice["text"] = sync.push(conn, storage)
    return response


def _parse_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


async def _store_uploads(document_id: int, uploads: list[UploadFile]) -> None:
    for upload in uploads:
        if not upload.filename:
            continue
        data = await upload.read()
        mime = upload.content_type or "application/octet-stream"
        key = storage.upload(upload.filename, mime, data)
        repo.add_file(conn, document_id, upload.filename, mime, len(data), key)


def _document_input(
    title: str,
    person_ids: list[int],
    tag_ids: list[int],
    languages: list[str],
    new_person: str,
    new_tag: str,
    doc_number: str,
    issuer: str,
    doc_date: str,
    expires_at: str,
    notes: str,
) -> DocumentInput:
    if new_person.strip():
        person_ids = person_ids + [repo.create_person(conn, new_person.strip()).id]
    if new_tag.strip():
        tag_ids = tag_ids + [repo.create_tag(conn, new_tag.strip()).id]
    return DocumentInput(
        title=title.strip(),
        person_ids=person_ids,
        tag_ids=tag_ids,
        languages=languages,
        doc_number=doc_number.strip(),
        issuer=issuer.strip(),
        doc_date=_parse_date(doc_date),
        expires_at=_parse_date(expires_at),
        notes=notes.strip(),
    )


@app.get("/login")
def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(
        request, "login.html", {"error": error, "google_configured": bool(settings.google_client_id)}
    )


@app.get("/setup")
def setup_page(request: Request):
    return templates.TemplateResponse(request, "setup.html", {"error": "", "done": False})


@app.post("/setup")
def apply_invite(request: Request, blob: str = Form(""), key: str = Form("")):
    try:
        invite.apply(blob.strip(), key.strip())
    except invite.InviteError as error:
        return templates.TemplateResponse(request, "setup.html", {"error": str(error), "done": False})
    return templates.TemplateResponse(request, "setup.html", {"error": "", "done": True})


@app.get("/invite")
def invite_page(request: Request):
    return templates.TemplateResponse(
        request, "invite.html", {"user": current_user(request), "blob": "", "key": "", "error": ""}
    )


@app.post("/invite")
def create_invite(request: Request):
    context = {"user": current_user(request), "blob": "", "key": "", "error": ""}
    if context["user"]["email"].lower() != settings.owner_email:
        context["error"] = "Приглашение может создать только владелец документов."
    else:
        try:
            context["blob"], context["key"] = invite.create()
        except invite.InviteError as error:
            context["error"] = str(error)
    return templates.TemplateResponse(request, "invite.html", context)


@app.get("/auth/local")
def auth_local(request: Request):
    """Door for trying the app before Google is set up; it closes once GOOGLE_CLIENT_ID exists."""
    if settings.google_client_id:
        return RedirectResponse("/login", status_code=303)
    request.session["email"] = settings.owner_email or "local@localhost"
    request.session["name"] = "Локальный вход"
    return RedirectResponse("/", status_code=303)


@app.get("/auth/start")
def auth_start(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    url = google_oauth.build_auth_url(settings.google_client_id, settings.redirect_uri, state)
    return RedirectResponse(url, status_code=303)


@app.get("/auth/callback")
def auth_callback(request: Request, code: str = "", state: str = ""):
    if not code or state != request.session.pop("oauth_state", None):
        return RedirectResponse("/login?error=Вход не удался, попробуйте ещё раз", status_code=303)

    user = google_oauth.exchange_code(
        settings.google_client_id, settings.google_client_secret, settings.redirect_uri, code
    )
    if not settings.may_log_in(user.email):
        return RedirectResponse(f"/login?error={user.email} нет в списке разрешённых", status_code=303)

    owner_without_drive = (
        settings.storage == "drive"
        and user.email.lower() == settings.owner_email
        and DRIVE_SCOPE not in user.granted_scopes
    )
    if owner_without_drive:
        return RedirectResponse(
            "/login?error=Не отмечена галочка доступа к Google Диску. Войдите ещё раз и отметьте её",
            status_code=303,
        )

    # Files live in the owner's Drive, so only the owner's refresh token is worth keeping.
    if user.email.lower() == settings.owner_email and user.refresh_token:
        local_state.update(drive_refresh_token=user.refresh_token)
        notice["text"] = sync.enable_after_login(storage)

    request.session["email"] = user.email
    request.session["name"] = user.name
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/")
def index(
    request: Request,
    q: str = "",
    person: list[int] = Query([]),
    tag: list[int] = Query([]),
    lang: list[str] = Query([]),
    expiring: str = "",
):
    filt = DocumentFilter(
        person_ids=person,
        tag_ids=tag,
        languages=lang,
        query=q,
        expiring_within_days=int(expiring) if expiring else None,
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "user": current_user(request),
            "docs": repo.search_documents(conn, filt, date.today()),
            "persons": repo.list_persons(conn),
            "tags": repo.list_tags(conn),
            "languages": LANGUAGES,
            "filt": filt,
            "today": date.today(),
        },
    )


@app.get("/documents/new")
def new_document_form(request: Request):
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "user": current_user(request),
            "doc": None,
            "persons": repo.list_persons(conn),
            "tags": repo.list_tags(conn),
            "languages": LANGUAGES,
            "error": None,
        },
    )


@app.post("/documents")
async def create_document(
    request: Request,
    title: str = Form(...),
    person: list[int] = Form([]),
    tag: list[int] = Form([]),
    lang: list[str] = Form([]),
    new_person: str = Form(""),
    new_tag: str = Form(""),
    doc_number: str = Form(""),
    issuer: str = Form(""),
    doc_date: str = Form(""),
    expires_at: str = Form(""),
    notes: str = Form(""),
    files: list[UploadFile] = File([]),
):
    data = _document_input(
        title, person, tag, lang, new_person, new_tag, doc_number, issuer, doc_date, expires_at, notes
    )
    document_id = repo.create_document(conn, data, created_by=current_user(request)["email"])
    await _store_uploads(document_id, files)
    return RedirectResponse(f"/documents/{document_id}", status_code=303)


@app.get("/documents/{document_id}")
def document_page(request: Request, document_id: int):
    doc = repo.get_document(conn, document_id)
    if doc is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "document.html",
        {"user": current_user(request), "doc": doc, "languages": LANGUAGES, "today": date.today()},
    )


@app.get("/documents/{document_id}/edit")
def edit_document_form(request: Request, document_id: int):
    doc = repo.get_document(conn, document_id)
    if doc is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "user": current_user(request),
            "doc": doc,
            "persons": repo.list_persons(conn),
            "tags": repo.list_tags(conn),
            "languages": LANGUAGES,
            "error": None,
        },
    )


@app.post("/documents/{document_id}")
def update_document(
    document_id: int,
    title: str = Form(...),
    person: list[int] = Form([]),
    tag: list[int] = Form([]),
    lang: list[str] = Form([]),
    new_person: str = Form(""),
    new_tag: str = Form(""),
    doc_number: str = Form(""),
    issuer: str = Form(""),
    doc_date: str = Form(""),
    expires_at: str = Form(""),
    notes: str = Form(""),
):
    data = _document_input(
        title, person, tag, lang, new_person, new_tag, doc_number, issuer, doc_date, expires_at, notes
    )
    repo.update_document(conn, document_id, data)
    return RedirectResponse(f"/documents/{document_id}", status_code=303)


@app.post("/documents/{document_id}/delete")
def delete_document(document_id: int):
    for key in repo.delete_document(conn, document_id):
        storage.delete(key)
    return RedirectResponse("/", status_code=303)


@app.post("/documents/{document_id}/files")
async def upload_files(document_id: int, files: list[UploadFile] = File([])):
    await _store_uploads(document_id, files)
    return RedirectResponse(f"/documents/{document_id}", status_code=303)


@app.get("/files/{file_id}")
def download_file(file_id: int):
    stored = repo.get_file(conn, file_id)
    if stored is None:
        return RedirectResponse("/", status_code=303)
    return Response(
        content=storage.download(stored.storage_key),
        media_type=stored.mime_type,
        headers={"Content-Disposition": f'inline; filename="{stored.filename}"'},
    )


@app.post("/files/{file_id}/delete")
def delete_file(request: Request, file_id: int):
    stored = repo.get_file(conn, file_id)
    if stored is None:
        return RedirectResponse("/", status_code=303)
    repo.delete_file(conn, file_id)
    storage.delete(stored.storage_key)
    return RedirectResponse(f"/documents/{stored.document_id}", status_code=303)
