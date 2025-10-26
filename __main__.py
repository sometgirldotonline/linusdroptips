APPVERSION = "0.3.6"
# Debug logging was added by Github Copilot
# yes this is literally the Goblintasks source code :sob:
from flask import (
    Flask,
    current_app,
    redirect,
    url_for,
    render_template,
    g,
    make_response,
    request,
    jsonify,
    session,
    send_file
)
import shutil
import jinja2
import os
import sqlite3
import json
import datetime, time
import secrets
import hashlib
import hmac
from datetime import datetime
import psutil
from dotenv import load_dotenv
from flask_dance.contrib.github import make_github_blueprint, github
import requests
from requests.auth import HTTPBasicAuth
startupTimeStamp = time.time()
load_dotenv()
app = Flask(__name__)
from collections import deque
# ensure datadir exists
if not os.path.exists(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "appdata.sqlite")
):
    print("Setting up datadir")
    shutil.copyfile(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "template-appdata.sqlite"),
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "appdata.sqlite"),
    )

# fix reverse proxies
from werkzeug.middleware.proxy_fix import ProxyFix

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config.from_mapping({"DEBUG": True})
# thing for reqs per sec calc
rpsTimestamps = deque(maxlen=1000)


@app.before_request
def track_request():
    rpsTimestamps.append(time.time())

def requests_per_second():
    now = time.time()
    # only count requests in the last second
    recent = [t for t in rpsTimestamps if now - t <= 1]
    return len(recent)



def get_db():
    if "db" not in g:
        if "github_id" not in session:
            return None
        user_db_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            f"appdata.sqlite",
        )
        g.db = sqlite3.connect(user_db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


app.secret_key = os.getenv("flaskDanceSecret")
ghblueprint = make_github_blueprint(
    client_id=os.getenv("githubClientID"),
    client_secret=os.getenv("githubClientSecret"),
)
# custom filter: convert unix timestamp -> datetime object for further formatting
@app.template_filter()
def timestamp_to_time(value):
    """Return a datetime object from a unix timestamp (seconds), or None on bad input."""
    if value is None or isinstance(value, jinja2.runtime.Undefined):
        return None
    try:
        t = float(value)
    except (TypeError, ValueError):
        return None
    # `datetime` is imported as the class (from datetime import datetime)
    return datetime.fromtimestamp(t)

@app.template_filter()
def datetimeformat(v, fmt='%Y-%m-%dT%H:%M:%S%z'):
    if isinstance(v, datetime):
        return v.strftime(fmt)
    return None
@app.template_filter()
def timestamp_to_datetime(value):
    # Return a datetime object or None for invalid input so datetimeformat can handle it
    if value is None or isinstance(value, jinja2.runtime.Undefined):
        return None
    try:
        t = float(value)
    except (TypeError, ValueError):
        return None
    # Use local time; switch to utcfromtimestamp if you want UTC
    return datetime.datetime.fromtimestamp(t)

@app.template_filter()
def getGithub(id, what):
    return github.get(f"/user/{id}").json()[what]
app.register_blueprint(ghblueprint, url_prefix="/login")

def generateUpdates(state, updates=[]):
    data = {
        "state": state,
        "pageUpdates": [
        ]
    }
    data["pageUpdates"]+=updates
    return data


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    res = make_response("Logged Out.")
    res.set_cookie("session", "", max_age=0)
    return res

@app.route("/login", methods=["GET"])
def login():
    if not github.authorized:
        return redirect(url_for("github.login"))
    else:
        return redirect("/")

@app.route("/", methods=["GET"])
def index():
    db = get_db()
    cur = db.cursor()
    if github.authorized and "github_id" not in session:
        resp = github.get("/user")
        assert resp.ok
        user_info = resp.json()
        session["github_id"] = user_info["id"]
        session["github_login"] = user_info["login"]
    if "analNoticeSeen" not in session:
        session["analNoticeSeen"] = False
    if "enableAnal" not in session:
        session["enableAnal"] = False
    dnt = request.headers.get("DNT") == "1"
    gpc = request.headers.get("Sec-GPC") == "1"
    if dnt or (gpc and "modifiedInSettings" not in session):
        session["enableAnal"] = False
        session["analNoticeSeen"] = True
    theme = ""
    if "theme" in session:
        theme = session["theme"]
    else:
        session["theme"] = "default"
    return render_template(
        "app.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
        drops=cur.execute("""SELECT *
FROM drops
ORDER BY id DESC
LIMIT 10;
""").fetchall()
    )

@app.route("/drop/<int:id>", methods=["GET"])
def drop(id):
    db = get_db()
    cur = db.cursor()
    if github.authorized and "github_id" not in session:
        resp = github.get("/user")
        assert resp.ok
        user_info = resp.json()
        session["github_id"] = user_info["id"]
        session["github_login"] = user_info["login"]
    if "analNoticeSeen" not in session:
        session["analNoticeSeen"] = False
    if "enableAnal" not in session:
        session["enableAnal"] = False
    dnt = request.headers.get("DNT") == "1"
    gpc = request.headers.get("Sec-GPC") == "1"
    if dnt or (gpc and "modifiedInSettings" not in session):
        session["enableAnal"] = False
        session["analNoticeSeen"] = True
    theme = ""
    if "theme" in session:
        theme = session["theme"]
    else:
        session["theme"] = "default"
    return render_template(
        "dropViewer.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
        drop=cur.execute("""SELECT *
FROM drops
WHERE id = ?
""", (id,)).fetchone(),
                drops=cur.execute("""SELECT *
FROM drops
ORDER BY id DESC
LIMIT 10;
""").fetchall()
    )


@app.route("/api/configureAnaylitics", methods=["POST"])
def configureAnaylitics():
    if not github.authorized:
        return redirect(url_for("github.login"))
    print(request.form["state"])
    if not session["analNoticeSeen"]:
        session["analNoticeSeen"] = True
    if request.form["modifiedInSettings"] == "true":
        session["modifiedInSettings"] = True
    if request.form["state"] == "true":
        print("enabling anal")
        session["enableAnal"] = True
        return generateUpdates("1$enabled")
    elif request.form["state"] == "false":
        print("disabling anal")
        session["enableAnal"] = False
        return generateUpdates("1$disabled")
@app.route("/api/health", methods=["GET"])
def healthAPI():
    ghApiStat = "unknown"
    try:
        r = requests.get("https://api.github.com", timeout=5)
        if r.status_code == 200:
            ghApiStat = "OK200"
        else:
            ghApiStat = f"CODE{r.status_code}"
    except requests.RequestException:
        ghApiStat = "unreachable"
    duTotal, duUsed, duFree = shutil.disk_usage("/")
    return {
        "uptime": time.time() - startupTimeStamp,
        "duPcent": (duUsed / duTotal) * 100,
        "githubAPI": ghApiStat,
        "cpuUsage": psutil.cpu_percent(interval=1),
        "appCPUusage": psutil.Process().cpu_percent(interval=1),
        "reqPerSec": format(requests_per_second(), ".2f")
    }   

@app.route("/api/setSessionData")
def sSD():
    if "key" in request.args and "value" in request.args:
        session[request.args["key"]] = request.args["value"]
        return session[request.args["key"]]
@app.route("/api/getSessionData")
def gSD():
    if "key" in request.args:
        return session[request.args["key"]]
    

if __name__ == "__main__":
    if os.getenv("PROTOCOL") == "HTTPS": 
        app.run(port=os.getenv("port"), ssl_context=(os.getenv("certfile"), os.getenv("keyfile")), debug=True)
    elif os.getenv("PROTOCOL") == "HTTP": 
        app.run(port=os.getenv("port"))
    