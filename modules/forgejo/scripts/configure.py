import os, pathlib, re, secrets

host = os.environ["FORGEJO_HOST"]
if not re.fullmatch(r"[a-zA-Z0-9.-]+\.ts\.net", host):
    raise ValueError("Check the Tailscale hostname")
target = pathlib.Path("/srv/forgejo/config/app.ini")
if target.exists():
    raise FileExistsError("Do not replace an existing config or regenerate its secrets")
config = f"""APP_NAME = Internal Forgejo
RUN_MODE = prod
RUN_USER = git
WORK_PATH = /var/lib/gitea

[database]
DB_TYPE = sqlite3
PATH = /var/lib/gitea/forgejo.db

[server]
PROTOCOL = http
HTTP_ADDR = 0.0.0.0
HTTP_PORT = 3000
DOMAIN = {host}
ROOT_URL = https://{host}:8443/
APP_DATA_PATH = /var/lib/gitea/data
OFFLINE_MODE = true
DISABLE_SSH = false
START_SSH_SERVER = true
SSH_DOMAIN = {host}
SSH_PORT = 2222
SSH_LISTEN_PORT = 2222
LFS_START_SERVER = true

[repository]
ROOT = /var/lib/gitea/git/repositories
DEFAULT_PRIVATE = private
FORCE_PRIVATE = true

[security]
INSTALL_LOCK = true
SECRET_KEY = {secrets.token_hex(32)}
INTERNAL_TOKEN = {secrets.token_hex(64)}
GLOBAL_TWO_FACTOR_REQUIREMENT = all
DISABLE_GIT_HOOKS = true
DISABLE_QUERY_AUTH_TOKEN = true
REVERSE_PROXY_LIMIT = 0

[service]
DISABLE_REGISTRATION = true
REQUIRE_SIGNIN_VIEW = true
ENABLE_BASIC_AUTHENTICATION = false
DEFAULT_USER_VISIBILITY = private
DEFAULT_ORG_VISIBILITY = private

[session]
COOKIE_SECURE = true
COOKIE_NAME = forgejo_session

[openid]
ENABLE_OPENID_SIGNIN = false
ENABLE_OPENID_SIGNUP = false

[mailer]
ENABLED = false

[packages]
ENABLED = true

[actions]
ENABLED = false

[log]
MODE = console
LEVEL = Info
"""
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    stream.write(config)
os.chown(target, 1000, 1000)
os.chmod(target, 0o600)
