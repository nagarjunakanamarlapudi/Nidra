"""`make google-oauth` — set up the platform-level Google OAuth client.

Google has no API to create an OAuth *client* headlessly (the "Create OAuth
client" button is Console-only), so that one click is irreducible. This wizard
automates everything around it: prints the exact redirect URI, opens the Console,
then writes the pasted ``client_id``/``client_secret`` plus ``OAUTH_REDIRECT_BASE_URL``
into ``.env`` so you never hand-edit it. One Google app covers all Google connectors.

The Calendar + Gmail APIs must be enabled **in the same project the OAuth client
lives in** — the #1 setup pitfall (a wrong-project "Enable" leaves you with a
working token but a 403 ``accessNotConfigured``). The client_id's leading segment
*is* that project number, so once you paste it we derive the project and open the
exact per-API enable pages (or run ``gcloud … --project <that project>``), removing
the guesswork entirely.
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import subprocess
import webbrowser
from pathlib import Path

CONSENT_URL = "https://console.cloud.google.com/apis/credentials/consent"
CREDENTIALS_URL = "https://console.cloud.google.com/apis/credentials"
GOOGLE_APIS = ("calendar-json.googleapis.com", "gmail.googleapis.com")


def project_number_from_client_id(client_id: str) -> str | None:
    """Extract the project number from a Google OAuth client id.

    Client ids look like ``<project-number>-<random>.apps.googleusercontent.com``;
    the leading all-digits segment is the project the client belongs to. Returns
    None if the id doesn't start with a numeric segment.
    """
    head = client_id.split("-", 1)[0].strip()
    return head if head.isdigit() else None


def api_overview_url(api: str, project: str) -> str:
    """The exact per-API 'enable' deep link, scoped to a project number."""
    return f"https://console.developers.google.com/apis/api/{api}/overview?project={project}"


def _open(url: str) -> None:
    """Best-effort open in a browser; callers always print the URL too (headless-safe)."""
    with contextlib.suppress(Exception):
        webbrowser.open(url)


def env_value(content: str, key: str) -> str | None:
    """Return the value of an uncommented ``KEY=value`` line, or None."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}=") and not stripped.startswith("#"):
            return stripped.split("=", 1)[1].strip()
    return None


def redirect_base(content: str) -> str:
    """The backend's local base URL, derived from APP_PORT (default 8000)."""
    return f"http://localhost:{env_value(content, 'APP_PORT') or '8000'}"


def redirect_uri(base: str) -> str:
    return f"{base.rstrip('/')}/connectors/oauth/callback"


def upsert_env(content: str, key: str, value: str) -> str:
    """Set ``key=value`` in ``.env`` text: replace an uncommented line in place,
    else append. Other lines (incl. comments) are preserved."""
    target = f"{key}="
    out: list[str] = []
    replaced = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(target) and not stripped.startswith("#"):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    text = "\n".join(out)
    return text if text.endswith("\n") else text + "\n"


def _enable_apis_via_gcloud(gcloud: str, project: str) -> bool:
    """Enable both APIs in `project` via gcloud. Returns True on success."""
    cmd = [gcloud, "services", "enable", *GOOGLE_APIS, "--project", project]
    print(f"  running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)  # noqa: S603 — gcloud is a resolved path
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"  ! gcloud couldn't enable the APIs ({exc}); use the Console links below.")
        return False
    return True


def _enable_apis(project: str | None) -> None:
    """Ensure Calendar + Gmail are enabled in the *client's* project.

    Tries gcloud (scoped to `project`) first; always falls back to opening the
    exact per-API enable pages so the user can't enable the wrong project.
    """
    if project is None:
        print("\n• Couldn't read the project from that client id. In the Console, enable")
        print("  'Google Calendar API' AND 'Gmail API' in the SAME project as this client.")
        return

    gcloud = shutil.which("gcloud")
    if gcloud:
        prompt = f"Enable Calendar + Gmail APIs via gcloud in project {project}? [y/N] "
        if input(prompt).strip().lower() == "y" and _enable_apis_via_gcloud(gcloud, project):
            print("  ✓ APIs enabled.")
            return

    print(f"\n• Enable BOTH APIs in project {project} (click 'Enable' if not already on):")
    for api in GOOGLE_APIS:
        url = api_overview_url(api, project)
        print(f"    {url}")
        _open(url)
    input("  Press Enter once BOTH pages show 'Manage' (i.e. enabled)… ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set up the platform Google OAuth client.")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args(argv)

    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"✗ {env_path} not found — run 'make setup' first.")
        return 1
    content = env_path.read_text()
    base = redirect_base(content)
    uri = redirect_uri(base)

    print("\n── Pragya · Google OAuth platform setup ──\n")
    print("Google has no API to create the OAuth client itself, so there's one manual")
    print("click ('Create OAuth client'). Everything else is automated.\n")
    print(f"Redirect URI to register (copy EXACTLY):\n  {uri}\n")

    print("Opening the Google Cloud Console…")
    print(f"  1. Consent screen ({CONSENT_URL}) → External → add yourself as a Test user.")
    print(f"  2. Credentials ({CREDENTIALS_URL}) → Create credentials → OAuth client ID")
    print("     → Web application → add the redirect URI above under 'Authorized redirect URIs'.\n")
    for url in (CONSENT_URL, CREDENTIALS_URL):
        _open(url)

    client_id = input("Paste the OAuth Client ID: ").strip()
    client_secret = input("Paste the OAuth Client Secret: ").strip()
    if not client_id or not client_secret:
        print("✗ Both Client ID and Secret are required. Nothing written.")
        return 1

    # Enable the APIs in the SAME project the client belongs to (derived from the
    # client id) — this is the step that prevents the 403 accessNotConfigured trap.
    _enable_apis(project_number_from_client_id(client_id))

    content = upsert_env(content, "GOOGLE_OAUTH_CLIENT_ID", client_id)
    content = upsert_env(content, "GOOGLE_OAUTH_CLIENT_SECRET", client_secret)
    content = upsert_env(content, "OAUTH_REDIRECT_BASE_URL", base)
    env_path.write_text(content)

    print(f"\n✓ Wrote GOOGLE_OAUTH_CLIENT_ID / _SECRET and OAUTH_REDIRECT_BASE_URL to {env_path}.")
    print("  Next: 'make up' to redeploy, then Connectors → Connect (Calendar / Gmail).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
