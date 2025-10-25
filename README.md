# LinusDropTips - Database of everything Linus has ever dropped
bweh
This repository is a minimal Flask starter with GitHub OAuth (Flask-Dance) and SQLite.

Environment and .env usage

For local development you can use a `.env` file to store environment variables. This repository includes a safe `env` example file `.env.example` that you should copy to `.env` and fill with your values. Never commit your real `.env` file — it's in `.gitignore`.

Example `.env` (copy from `.env.example`):

GITHUB_OAUTH_CLIENT_ID=your_client_id
GITHUB_OAUTH_CLIENT_SECRET=your_client_secret
SECRET_KEY=replace-with-a-secret

The app auto-loads `.env` at startup using `python-dotenv`. In production, prefer real environment variables or a secret manager instead of a `.env` file.

Quick start

1. Create & activate a venv and install deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill values.

3. Run the app:

```bash
python3 __main__.py
```

Open http://localhost:5000 and click "Log in with GitHub" to authenticate.

Security notes

- Do NOT commit `.env` with real secrets. Use `.env.example` in the repo to document required variables.
- In production use environment variables supplied by your host, CI secrets, or a secret manager.