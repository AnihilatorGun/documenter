import os
import tempfile

# Must happen before documenter.config is imported: settings are read at import time.
# Set explicitly rather than left blank, so a real .env cannot leak into the tests.
_tmp = tempfile.mkdtemp(prefix="documenter-tests-")
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["LOCAL_FILES_DIR"] = os.path.join(_tmp, "files")
os.environ["STORAGE"] = "local"
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["OWNER_EMAIL"] = "owner@example.com"
os.environ["ALLOWED_EMAILS"] = ""
