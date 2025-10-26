APPVERSION = "0.3.6"
USEFAKEHUB = False
# moderators
madawaderIds = ["47910472"]
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
from yt_dlp import YoutubeDL
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
import logging, traceback, secrets

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config.from_mapping({"DEBUG": True})
# thing for reqs per sec calc
rpsTimestamps = deque(maxlen=1000)

def getYTVidMeta(id):
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'force_generic_extractor': True,  # sometimes faster
        'extract_flat': True,             # don’t resolve formats/streams
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(id, download=False)
        return {"title": info.get("title"), "handle": info.get("uploader_id"), "pStamp": int(datetime.strptime(info.get("upload_date"), "%Y%m%d").timestamp())}
    return "failed"

def hmsToSeconds(hms):
    h, m, s = map(int, hms.split(":"))
    return (h * 3600) + (m * 60) + s

def has_all_keys_set(obj, required_keys):
    return set(required_keys).issubset(obj.keys())
def all_keys_have_values(obj, required_keys):
    return all(k in obj and obj[k] not in (None, '') for k in required_keys)

@app.before_request
def track_request():
    rpsTimestamps.append(time.time())

def requests_per_second():
    now = time.time()
    # only count requests in the last second
    recent = [t for t in rpsTimestamps if now - t <= 1]
    return len(recent)

db = None

def get_db():
    global db
    if db == None:
        db = sqlite3.connect(os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            f"appdata.sqlite",
        ))
        db.row_factory = sqlite3.Row
    return db


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

githubIdMap = {}

# fake Github with fixed responses for everything because I need a way to work offline
class fakeHub:
    @staticmethod
    def get(path):
        return {"login":"offlinedevelopmentuser", "id":69}


@app.template_filter()
def getGithub(id, what):
    id = str(id)
    if id in githubIdMap:
        return githubIdMap[id][what]
    else:
        if USEFAKEHUB:
            data = fakeHub.get("")
        else:
            data =  github.get(f"/user/{id}").json()
        githubIdMap[id] = data
        return data[what]
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
    res = make_response("<script>setTimeout(()=>{window.navigation.back()}, 1500)</script>Logged Out. Taking you back to <script>document.writeln(document.referrer)</script>")
    res.set_cookie("session", "", max_age=0)
    return res

@app.route("/login", methods=["GET"])
def login():
    if not github.authorized:
        return redirect(url_for("github.login"))
    else:
        return redirect("/")

def prepareSession():
    if github.authorized and "github_id" not in session:
        if USEFAKEHUB:
            user_info = fakeHub.get("")
        else:
            resp = github.get("/user")
            assert resp.ok
            user_info = resp.json()
        session["github_id"] = user_info["id"]
        session["github_login"] = user_info["login"]
    if "github_id" in session and str(session["github_id"]) in madawaderIds:
        session["isModerator"] = True
    else:
        session["isModerator"] = False
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

@app.route("/", methods=["GET"])
def index():
    db = get_db()
    cur = db.cursor()
    prepareSession()
    return render_template(
        "app.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
        drops=cur.execute("""SELECT *
FROM drops
WHERE verificationStatus = 1
ORDER BY id DESC
LIMIT 10;
""").fetchall()
    )

@app.route("/search", methods=["GET"])
def search():
    if "q" not in request.args:
        return redirect("/")
    query = request.args["q"]
    db = get_db()
    cur = db.cursor()
    prepareSession()
    terms = query.split(" ")
    columns = "itemName,itemPrice,dropReason,droppedOnto,resultingDamage,approxDropHeight,itemType,itemCondition,componentType,submitterID,ytId,videoTitle,videoDate,startSeconds,submitDate".split(",")
    query_parts = []
    params = []
    for term in terms:
        for col in columns:
            query_parts.append(f"{col} LIKE ?")
            params.append(f"%{term}%" )
    return render_template(
        "search.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
        query=query,
        drops=cur.execute(f"""SELECT *
FROM drops
WHERE verificationStatus = 1 AND ({' OR '.join(query_parts)})
""", params).fetchall()
    )


@app.route("/drop/<int:id>", methods=["GET"])
def drop(id):
    db = get_db()
    cur = db.cursor()
    prepareSession()
    thisDrop = cur.execute("""SELECT *
FROM drops
WHERE id = ?
""", (id,)).fetchone()
    if thisDrop["verificationStatus"] != 1 and str(session["github_id"]) != str(thisDrop["submitterID"]):
        return "404 Drop Not Found"
    return render_template(
        "dropViewer.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
        drop=thisDrop,
                relatedDrops=cur.execute(""" SELECT *
    FROM drops
    WHERE verificationStatus = 1 AND  ytId = (
        SELECT ytId
        FROM drops
        WHERE id = ?
    )""", (id,)).fetchall(),
                drops=cur.execute("""SELECT *
FROM drops
WHERE verificationStatus = 1 AND id != ?
ORDER BY id DESC
LIMIT 10;
""", (id,)).fetchall(),
                userIsAuthor=str(session["github_id"]) == str(thisDrop["submitterID"])
    )


@app.route("/user/<int:id>", methods=["GET"])
def user(id):
    db = get_db()
    cur = db.cursor()
    prepareSession()
    uD = None
    userIsAuthor = False
    if github.authorized and "github_id" in session and str(session["github_id"]) == str(id):
        uD = cur.execute(""" SELECT *
    FROM drops
    WHERE submitterID = ?""", (session["github_id"],)).fetchall()
        userIsAuthor = True
    else:
        uD = cur.execute(""" SELECT *
    FROM drops
    WHERE verificationStatus = 1 AND submitterID = ?""", (id,)).fetchall()
    return render_template(
        "user.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
        userDrops=uD,
        userID=id,
        userIsAuthor=userIsAuthor
    )

@app.route("/madawader", methods=["GET"])
def madawader():
    db = get_db()
    cur = db.cursor()
    prepareSession()
    if "github_id" not in session or not session.get("isModerator", False) or str(session["github_id"]) not in madawaderIds:
        return "denied"
    return render_template(
        "moderator.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
        drops=cur.execute(""" SELECT *
    FROM drops""").fetchall(),
        userID=id,
    )

@app.route("/madawader/drop/<int:id>", methods=["GET"])
def madawaderdrop(id):
    db = get_db()
    cur = db.cursor()
    prepareSession()
    if "github_id" not in session or not session.get("isModerator", False) or str(session["github_id"]) not in madawaderIds:
        return "denied"
    thisDrop = cur.execute("""SELECT *
FROM drops
WHERE id = ?
""", (id,)).fetchone()
    if thisDrop["verificationStatus"] != 1 and str(session["github_id"]) != str(thisDrop["submitterID"]):
        return "404 Drop Not Found"
    return render_template(
        "madawaderDropViewer.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
        drop=thisDrop
    )

@app.route("/submit", methods=["GET"])
def submit():
    db = get_db()
    cur = db.cursor()
    prepareSession()
    return render_template(
        "submit.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
    )

@app.route("/submit/form", methods=["GET"])
def submitForm():
    db = get_db()
    cur = db.cursor()
    if not github.authorized:
        return redirect(url_for("github.login"))
    prepareSession()
    if not(has_all_keys_set(request.args, [
    "vidid",
    "droptitle",
    "cost",
    "reason",
    "droppedOnto",
    "damage",
    "approxDropHeight",
    "itemType",
    "itemCondition",
    "componentType",
    "videoTimestamp",
])):
        return "bitch youre missing a key try again"
    if not(all_keys_have_values(request.args,[
    "vidid",
    "droptitle",
    "cost",
    "reason",
    "droppedOnto",
    "damage",
    "approxDropHeight",
    "itemType",
    "itemCondition",
    "componentType",
    "videoTimestamp",
])):
        return "why are you trying to submit manually (or your browser is drunk). go back and try again, you forgot something (its empty)"
    videoInfo = getYTVidMeta(request.args["vidid"])
    if videoInfo["handle"].lower() not in ["@linustechtips",
"@shortcircuit",
"@techquickie",
"@techlinked",
"@gamelinked",
"@macaddress",
"@lmgclips",
"@channelsuperfun",
"@theyrejustmovies"]:
        return "Sorry, that video is not from an official LTT channel, please contact me on Telegram (@sometgirldotonline)"
    try:
        r = db.execute(f"""INSERT INTO drops (
                      startSeconds,
                      videoDate,
                      videoTitle,
                      ytId,
                      submitterID,
                      verificationStatus,
                      componentType,
                      itemCondition,
                      itemType,
                      approxDropHeight,
                      resultingDamage,
                      droppedOnto,
                      dropReason,
                      itemPrice,
                      itemName,
                      note
                  )
                  VALUES (
                      ?,
                      ?,
                      ?,
                      ?,
                      ?,
                      0,
                      ?,
                      ?,
                      ?,
                      ?,
                      ?,
                      ?,
                      ?,
                      ?,
                      ?,
                      ?
                  );
""", (hmsToSeconds(request.args["videoTimestamp"]), videoInfo["pStamp"], videoInfo["title"], request.args["vidid"], session["github_id"], request.args["componentType"], request.args["itemCondition"], request.args["itemType"], request.args["approxDropHeight"], request.args["damage"], request.args["droppedOnto"], request.args["reason"], request.args["cost"], request.args["droptitle"], request.args["notes"]  ))
        db.commit()
        
        return render_template(
        "submitted.html",
        showAnayliticsNotice=not session["analNoticeSeen"],
        enableAnal=session["enableAnal"],
        host=os.getenv("APPHOST"),
        session=session,
        loggedIn=github.authorized,
    )
    except Exception as e:
        err_id = secrets.token_hex(8)
        logging.exception("submitForm error (id=%s): %s", err_id, traceback.format_exc())

        # try to rollback DB work if possible
        try:
            if "db" in locals() and db is not None:
                db.rollback()
        except Exception:
            logging.exception("Rollback failed for error id %s", err_id)

        # return a generic, non-sensitive error to the client with a reference id
        res = make_response(f"Internal server error. Reference: {err_id}", 500)
        return res
    



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

@app.route("/madawader/updatedrop", methods=["GET"])
def etphonehome():
    required = [
    "id",
    "itemName",
    "startSeconds",
    "videoTitle",
    "ytId",
    "verificationStatus",
    "rejectionNotice",
    "videoDate",
    "submitDate",
    "itemPrice",
    "dropReason",
    "droppedOnto",
    "resultingDamage",
    "approxDropHeight",
    "itemType",
    "itemCondition",
    "componentType",
    "submitterID",
    "note"
]
    data = request.args or request.form

    if any(
        k not in request.args
        or str(request.args.get(k)).strip().lower() in ("", "none", "null")
        for k in required
    ):

        if not github.authorized:
            return redirect(url_for("github.login"))
        if not session["isModerator"]:
            return "kindly go fuck yourself."
        db = get_db()
        try:
            modify = []
            attributetuple = ();
            for attr in required:
                    
                if attr != id:
                    modify.append(f"{attr} = ?")
                if request.args.get(attr).lower().strip() == "none":
                    attributetuple = attributetuple + (None,)
                else:
                    attributetuple = attributetuple + (request.args.get(attr),)
            attributetuple = attributetuple + (request.args.get("id"),)
            cur = db.execute(
                f"""
            UPDATE drops
            SET {", ".join(modify)}
            WHERE id = ?;
            """,
                attributetuple,
            )
            db.commit()
        except Exception as e:
            return make_response(e)

        return make_response("<script>setTimeout(()=>{window.navigation.back()}, 1500)</script>Modified successfully. Taking you back to <script>document.writeln(document.referrer)</script>")
    else:
        print(request.args)
        return f"Missing: {[
    k for k in required
    if k not in request.args
    or str(request.args.get(k)).strip().lower() in ("", "none", "null")
]}"


    

if __name__ == "__main__":
    if os.getenv("PROTOCOL") == "HTTPS": 
        app.run(port=os.getenv("port"), ssl_context=(os.getenv("certfile"), os.getenv("keyfile")), debug=True)
    elif os.getenv("PROTOCOL") == "HTTP": 
        app.run(port=os.getenv("port"))
    