# Security Policy

## Scope & posture

Pragya is a single-user, self-hosted personal assistant. It is read-only with respect to financial data (Plaid read-only access; no money-movement APIs are used). Secrets (API keys, access tokens) are encrypted at rest in the database using the `cryptography` library.

## Reporting a vulnerability

If you discover a security vulnerability, please **do not open a public GitHub issue**.

Send a report to: **nagarjuna@aadhaa.in** with the subject line `[SECURITY] Pragya vulnerability report`.

Include:
- A description of the issue and its potential impact
- Steps to reproduce or a proof-of-concept
- Affected component(s) and version

You will receive an acknowledgement within 5 business days. Because this is a single-maintainer project, fixes are prioritised by severity and may take longer than enterprise response windows.

## Automated security controls

The following checks run automatically on every push and pull request via GitHub Actions:

| Check | Tool | Blocking? |
|---|---|---|
| Secret scanning (commits) | [Gitleaks](https://github.com/gitleaks/gitleaks) | Yes |
| Private-key detection | pre-commit-hooks `detect-private-key` | Yes (pre-commit) |
| Python SAST | ruff `S` rules (flake8-bandit) + Bandit | Yes (lint gate) |
| Python dependency CVEs | `pip-audit` | Informational |
| Frontend dependency CVEs | `npm audit --audit-level=high` | Informational |
| Dependabot | Weekly PRs for pip / npm / docker / actions | Automatic |

Install the pre-commit hooks locally with `make hooks` — they run gitleaks, private-key checks, and ruff on every commit.
