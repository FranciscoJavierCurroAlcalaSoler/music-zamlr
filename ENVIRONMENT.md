# Music Zamlr — Development Environment

Reproducible inventory of the dev/runtime setup. Update whenever something is installed, upgraded, or reconfigured. Language-level packages are tracked by their lockfiles, not here — see "Not tracked here" at the bottom.

Last updated: 2026-07-01

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

## VS Code extensions
| Extension | Publisher | Purpose |
|---|---|---|
| Python | Microsoft | Python support; pulls in Pylance + Python Debugger |
| ESLint | Microsoft | JS/TS linting |
| Prettier - Code formatter | Prettier | Auto-format on save |
| Vim | vscodevim | Vim keybindings inside VS Code |

Extension versions float on auto-update; pin one only if it ever matters.

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

System binaries that *do* belong here later (no lockfile covers them):
- Chromaprint / `fpcalc` (Phase 5, fingerprinting)

## Rebuilding from a clone
After `git clone`:
- Backend: `cd backend`, `py -m venv .venv`, activate it, `pip install -r requirements.txt`.
- Frontend: `cd frontend`, `npm install`.
- Run (two terminals): backend `fastapi dev main.py` (serves `:8000`); frontend `npm run dev` (serves `:5173`).
