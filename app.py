import os, secrets
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, abort, send_from_directory
from werkzeug.utils import secure_filename

try:
    from supabase import create_client
except ImportError:
    create_client = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

VAULT_PASSWORD = os.environ.get("VAULT_PASSWORD", "NoshUin2026")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = os.environ.get("SUPABASE_BUCKET", "private-memories")

# Demo/local mode keeps files on disk. For online deployment, use Supabase.
LOCAL_DIR = Path(__file__).resolve().parent / "uploads"
LOCAL_DIR.mkdir(exist_ok=True)
local_items = []

def sb():
    if not (SUPABASE_URL and SUPABASE_KEY and create_client):
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def ok():
    return session.get("vault_ok") is True

def media_list():
    client = sb()
    if client:
        res = client.storage.from_(BUCKET).list(path="", options={"sortBy":{"column":"created_at","order":"desc"}})
        return [{"filename": x.get("name"), "original_name": x.get("name",""), "kind": "video" if x.get("name","").lower().endswith((".mp4",".webm",".mov")) else "audio"} for x in (res or []) if x.get("name")]
    return list(reversed(local_items))

@app.route("/", methods=["GET","POST"])
def login():
    if ok(): return redirect(url_for("vault"))
    error = None
    if request.method == "POST":
        p = request.form.get("password","")
        if secrets.compare_digest(p, VAULT_PASSWORD):
            session["vault_ok"] = True
            return redirect(url_for("vault"))
        error = "Wrong password."
    return render_template("login.html", error=error)

@app.route("/vault")
def vault():
    if not ok(): return redirect(url_for("login"))
    return render_template("vault.html", media=media_list())

@app.route("/upload", methods=["POST"])
def upload():
    if not ok(): abort(403)
    f = request.files.get("file")
    if not f or not f.filename: return redirect(url_for("vault"))
    ext = Path(f.filename).suffix.lower()
    allowed = {".mp4",".webm",".mov",".mp3",".m4a",".wav",".ogg",".aac"}
    if ext not in allowed: return "Unsupported file type", 400
    safe = secrets.token_hex(12) + ext
    data = f.read()
    client = sb()
    if client:
        client.storage.from_(BUCKET).upload(safe, data, {"content-type": f.mimetype or "application/octet-stream"})
    else:
        (LOCAL_DIR/safe).write_bytes(data)
        local_items.append({"filename":safe, "original_name":secure_filename(f.filename), "kind":"video" if ext in {".mp4",".webm",".mov"} else "audio"})
    return redirect(url_for("vault"))

@app.route("/media/<path:name>")
def media(name):
    if not ok(): abort(403)
    client = sb()
    if client:
        # A short-lived signed URL keeps the bucket private.
        signed = client.storage.from_(BUCKET).create_signed_url(name, 120)
        url = signed.get("signedURL") or signed.get("signedUrl")
        if not url: abort(404)
        from flask import redirect as flask_redirect
        return flask_redirect(url)
    return send_from_directory(LOCAL_DIR, name)

@app.route("/delete/<path:name>", methods=["POST"])
def delete(name):
    if not ok(): abort(403)
    client = sb()
    if client:
        client.storage.from_(BUCKET).remove([name])
    else:
        try: (LOCAL_DIR/name).unlink()
        except FileNotFoundError: pass
        local_items[:] = [x for x in local_items if x["filename"] != name]
    return redirect(url_for("vault"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=False)
