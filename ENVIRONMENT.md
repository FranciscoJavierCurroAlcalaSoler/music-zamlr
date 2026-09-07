# Music Zamlr — Development Environment

Reproducible inventory of the dev/runtime setup. Update whenever something is installed, upgraded, or reconfigured. Language-level packages are tracked by their lockfiles, not here — see "Not tracked here" at the bottom.

Last updated: 2026-09-04

## Machine
| | |
|---|---|
| Device | Windows 10 notebook (dev + runtime) |
| Role | Runs the FastAPI backend; music drives attach here. Also the coding machine. iPad Pro = optional browser client over the LAN. |

## Languages & runtimes
| Item | Version | Installed via |
|---|---|---|
| Python | 3.14.6 | Python Install Manager (`py install 3.14`) |
| Node.js | 24.18.0 (Active LTS) | Official LTS installer (bundles npm) |

## Tools
| Item | Version | Notes |
|---|---|---|
| Git | 2.55.0 | Terminal: MinTTY. Credential helper: Git Credential Manager. |
| VS Code | 1.127.0 | Display language pinned to English (`locale: en`). |
| GitHub CLI (`gh`) | 2.100.0 | Added 2026-09-04, `winget install --id GitHub.cli`. Reads Actions run logs without a browser: `gh run view --log-failed`. Authenticated over HTTPS. **Not** set as Git's credential helper — `gh auth login` offers to take that role and was declined, so Git Credential Manager keeps it. |
| Chromaprint (`fpcalc`) | 1.6.1 (FFmpeg Lavc62.11.100) | Added 2026-09-05, `winget install --id AcoustID.Chromaprint --exact`. The fingerprinting binary for Phase 5. No lockfile covers it, which is why it is here. Installed as a winget *portable* package: the exe lands under `%LOCALAPPDATA%\Microsoft\WinGet\Packages\AcoustID.Chromaprint_.../chromaprint-fpcalc-1.6.1-windows-x86_64\` and is reachable on PATH only in shells started after the install. Locate it in code with `shutil.which("fpcalc")`, the only form that honours `PATHEXT` and so finds `fpcalc.exe`. This is the **x86_64** build. **CI pins this same 1.6.1 and installs it from the project's own GitHub release on all three runners** rather than from a package manager, so every leg tests the version this machine has — see `FPCALC_VERSION` in `.github/workflows/ci.yml`, and move the two together or neither. Package managers were rejected for that reason: apt's `libchromaprint-tools` and Homebrew's `chromaprint` each ship whatever their distribution froze, and Chocolatey's `chromaprint` is stuck at **1.1**, over a decade old. |
| ffmpeg | 8.1.2 (Gyan full build) | Not installed for the app — it generates the manual test collections (the two `make_fixtures*.sh` scripts) and the synthetic fixtures under `backend/tests/fixtures/`. Recorded 2026-09-05 because nothing else names it and a clone cannot rebuild those collections without it. The app itself shells out to `fpcalc`, never to ffmpeg; see the spec's Phase 5 entry for why that choice was made. |

## VS Code extensions
Verified against `code --list-extensions` on 2026-09-07. Check with that
command rather than trusting this table — see the sync note below.

| Extension | Identifier | Purpose |
|---|---|---|
| Python | `ms-python.python` | Python support; pulls in Pylance, Debugpy and Python Environments |
| Ruff | `charliermarsh.ruff` | Python formatting and lint diagnostics in the editor |
| ESLint | `dbaeumer.vscode-eslint` | JS/TS linting |
| Prettier - Code formatter | `esbenp.prettier-vscode` | Auto-format on save |
| GitHub Actions | `github.vscode-github-actions` | Workflow syntax and run status |
| Vim | `vscodevim.vim` | Vim keybindings inside VS Code |

Extension versions float on auto-update; pin one only if it ever matters.

**Three of these went missing once, and nothing said so** (2026-09-07). Ruff,
ESLint and Prettier were all absent while `.vscode/settings.json` still named
them as formatters. The suspected cause is Settings Sync: `code tunnel` was
set up across the notebook and the tablet, and a sync from the device with
the shorter extension list wins silently. **The failure is quiet by
construction** — VS Code does not warn that a configured `defaultFormatter`
is not installed, so format-on-save simply stops happening and every file
looks fine until CI or a manual `ruff` run disagrees. If formatting ever
seems not to run, check the extension list first and the settings second.

**Ruff in the editor is not the same tool as `ruff` in CI.** The extension
formats and shows diagnostics; the pinned `ruff` in `backend/requirements.txt`
is what the workflow runs. They can drift apart in version, and only the
second one can fail a build.

Prettier is the exception, and is pinned as an exact devDependency in
`frontend/package.json`. The extension bundles its own copy but prefers a
workspace-local install, so pinning is what keeps the editor and `npx prettier`
on the same version. Without it the two drifted and disagreed about formatting,
so files reformatted themselves back and forth between a save and a CLI run.

Format-on-save is configured per language in `.vscode/settings.json`: Prettier
for TS/TSX/CSS/JSON, Ruff for Python. Markdown is deliberately excluded —
Prettier realigns every table in these docs, which is diff noise rather than a
fix.

**Format-on-save is not lint-on-save, and the difference matters.**
`ruff format` handles whitespace and line breaks only. `ruff check` is a
separate tool with separate rules, and `editor.codeActionsOnSave` is what
brings any of it to a save. Even then it applies only the fixes ruff marks
*safe*: `if x == None:` is left exactly as written, because rewriting a
comparison changes behaviour in cases ruff will not decide for you. The
editor squiggle is what catches that one, not the save. Both actions are
named `source.fixAll.ruff` and `source.organizeImports.ruff` rather than the
unsuffixed forms, because Pylance also answers `organizeImports` for Python
and the plain name leaves the winner unspecified.

**Line endings are pinned to LF in two places, and both are needed** (added
2026-08-13). Every text file in the repo is stored as LF, but Git's
`core.autocrlf=true` rewrites them to CRLF on checkout, and Prettier's
`endOfLine` defaults to `lf` — so a fresh clone failed
`npx prettier --check src/` on files nobody had touched.

- `.gitattributes` (`* text=auto eol=lf`) governs files **Git** writes. Being
  committed, it applies on every machine whatever that machine's
  `core.autocrlf` is set to, so no per-developer Git config is required.
  `text=auto` still lets Git detect binaries, so the audio fixtures under
  `backend/tests/fixtures/` are untouched.
- `"files.eol": "\n"` in `.vscode/settings.json` governs files the **editor**
  creates, which no checkout rule ever sees. VS Code on Windows creates new
  files with `\r\n`, and format-on-save does not rescue them: Prettier
  normalizes the content while the editor writes the endings. Two new
  components failed the format check on their first save before this was set.

## Git configuration (global)
```
user.name          = Curro
user.email         = 254643964+FranciscoJavierCurroAlcalaSoler@users.noreply.github.com
init.defaultBranch = main
core.editor        = code --wait
```
Credential helper: Git Credential Manager (set by the installer).

## Repository
| | |
|---|---|
| Remote | github.com/<username>/music-zamlr (private) |
| Contents | Phase 0 scaffold committed: `backend/` (FastAPI skeleton + venv, `requirements.txt`) and `frontend/` (Vite React+TS, `package.json`), combined root `.gitignore`, README, this file. No LICENSE yet (parked; MIT lean). |

## Setup choices worth remembering
- Node installer "Tools for Native Modules" left unchecked (not needed; revisit only on a native-build error).
- Python 3.14 chosen; 3.13 was the conservative alternative. The whole stack supports both.

## Not tracked here (by design)
These are captured by their own files and should not be duplicated here:
- Python packages → `backend/requirements.txt` (or `pyproject.toml`)
- Node packages → `frontend/package.json` + `package-lock.json`

System binaries have no lockfile, so they live in the Tools table above:
`fpcalc` and `ffmpeg` are both recorded there as of 2026-09-05.

**Regenerating `requirements.txt` on Windows: mind the encoding.** The file
was stored as UTF-16LE with a BOM until 2026-09-05, because `pip freeze >
requirements.txt` under Windows PowerShell 5.1 writes UTF-16 for `>`
redirection. pip itself copes — it sniffs the BOM — so nothing was visibly
broken for months. What broke quietly: `.gitattributes`' `* text=auto eol=lf`
classifies the file as **binary** on account of the interleaved NUL bytes, so
it was excluded from line-ending normalization and rendered as an unreadable
blob in every diff, and any consumer without pip's BOM sniffing (uv, a
non-pip Docker build, some dependency scanners) would have failed on it. Now
plain UTF-8. To keep it that way, redirect explicitly:

```
pip freeze | Out-File -Encoding utf8 requirements.txt
```

## Rebuilding from a clone
After `git clone`:
- Backend: `cd backend`, `py -m venv .venv`, activate it, `pip install -r requirements.txt`.
- Frontend: `cd frontend`, `npm install`.
- Run (two terminals): backend `fastapi dev main.py` (serves `:8000`); frontend `npm run dev` (serves `:5173`).
