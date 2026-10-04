# Music Zamlr — Development Environment

The tools on the development machine, at the versions in use. Update this file
when you install, upgrade, or reconfigure a tool. Python and npm packages are
in their lockfiles, not here (see [Not tracked here](#not-tracked-here)).
To run or build the project from a clone, read [CONTRIBUTING.md](CONTRIBUTING.md).

Last updated: 2026-10-04

## Machine

| | |
|---|---|
| Device | Windows 10 notebook |
| Role | The coding machine. It also runs the program, and the music drives connect to it. |

## Languages and runtimes

| Item | Version | Installed with |
|---|---|---|
| Python | 3.14.8 | Python Install Manager (`py install 3.14`). Update with `py install --update 3.14`, then `py -m venv --upgrade backend\.venv`. |
| Node.js | 24.21.0 (Active LTS), npm 11.19.0 | The official Windows Installer (`.msi`) from nodejs.org, which includes npm. Install a newer version over the old one with the same installer. |
| Rust | rustc 1.99.0, rustup 1.29.1 | `winget install --id Rustlang.Rustup --exact`. Default toolchain `stable-x86_64-pc-windows-msvc`. Only the desktop shell needs it. `cargo` is on `PATH` only in shells started after the installation. **The Rust build needs an antivirus exclusion on this machine**: see [Building the shell](#building-the-shell-an-antivirus-exclusion-is-necessary). |

## Tools

| Item | Version | Notes |
|---|---|---|
| Git | 2.55.0 | Terminal: MinTTY. Credential helper: Git Credential Manager. |
| VS Code | 1.127.0 | Display language set to English (`locale: en`). |
| GitHub CLI (`gh`) | 2.100.0 | `winget install --id GitHub.cli`. Reads Actions logs without a browser: `gh run view --log-failed`. Authenticated over HTTPS. It is **not** Git's credential helper: Git Credential Manager has that role. |
| Chromaprint (`fpcalc`) | 1.6.1 (FFmpeg Lavc62.11.100), x86_64 | `winget install --id AcoustID.Chromaprint --exact`. A winget *portable* package: the executable is under `%LOCALAPPDATA%\Microsoft\WinGet\Packages\AcoustID.Chromaprint_...\chromaprint-fpcalc-1.6.1-windows-x86_64\`, and it is on `PATH` only in shells started after the installation. Find it in code with `shutil.which("fpcalc")`, the only form that applies `PATHEXT` and so finds `fpcalc.exe`. This installation is for running from source. **The desktop program ships its own copy** in `frontend/src-tauri/binaries/fpcalc.exe` and passes it to the backend as `ZAMLR_FPCALC`. **All copies must be the version that `FPCALC_VERSION` names** in `.github/workflows/ci.yml` and `release.yml`. CI downloads that version from Chromaprint's own GitHub release on all three runners. Package managers do not pin it: apt and Homebrew ship whatever version their distribution holds, and Chocolatey's `chromaprint` is version 1.1. |
| ffmpeg | 8.1.2 (Gyan full build) | Not used by the program, which calls `fpcalc` and never ffmpeg. It makes the manual test collections (the two `make_fixtures*.sh` scripts) and the synthetic fixtures under `backend/tests/fixtures/`. |
| Visual Studio 2022 Build Tools | MSVC 14.44.35207, Windows SDK 10.0.26100.0 | `winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"`. Several gigabytes, and it needs administrator rights. Rust on Windows links with `link.exe` from these tools. Without them, `rustc` stops with "linker `link.exe` not found". VS Code is not a replacement. **The MSVC toolset installs before the Windows SDK, and linking fails until both are present.** |
| cargo-about | 0.9.2 | `cargo install cargo-about --features cli`. **The `cli` feature is necessary**: without it, the installation builds no binary, and `cargo about` reports "no such command". It reads `Cargo.lock` and writes the notices for the Rust crates from `src-tauri/about.hbs`. It is a build tool, so it is not a dependency in `Cargo.toml`, which would ship it with the program. **The release workflow installs the same version and generates the notices itself.** On this machine it is only for a preview, into the gitignored `src-tauri/THIRD-PARTY-RUST.txt`. |
| Monkey's Audio | 13.26 (x64) | The official installer `MAC_1326_x64.exe` from monkeysaudio.com. No checksum is published. The Authenticode signature is valid, signer Matthew Ashland. Folder: `C:\Program Files\Monkey's Audio x64\`. **Not on `PATH`**, so call `MAC.exe` with its full path. Not used by the program: `MAC.exe` encodes the fixture `backend/tests/fixtures/test_track.ape`, which ffmpeg cannot encode. |

## Building the shell: an antivirus exclusion is necessary

`frontend/src-tauri/target` is excluded in **FortiClient AntiVirus**. Without
the exclusion, no Rust build on this machine can link:

```
LINK : fatal error LNK1105: cannot close file ...dll.exp. error code 1224
```

Error 1224 is `ERROR_USER_MAPPED_FILE`: another process holds the import
library that the linker wrote. Rust creates and deletes thousands of
short-lived files in `target/`. An on-access scanner that opens each one
collides with the linker. The Windows search indexer and parallel linking are
not the cause.

Windows Defender needs **no** exclusion. Everything in `target/` is build
output, made again from source.

CI has no such scanner, so CI cannot show this problem.

## VS Code extensions

Make sure that this table agrees with `code --list-extensions`. Settings Sync
can remove extensions without a warning (see below).

| Extension | Identifier | Purpose |
|---|---|---|
| Python | `ms-python.python` | Python support. It also installs Pylance, Debugpy and Python Environments. |
| Ruff | `charliermarsh.ruff` | Python formatting and lint diagnostics in the editor |
| ESLint | `dbaeumer.vscode-eslint` | JS/TS lint |
| Prettier - Code formatter | `esbenp.prettier-vscode` | Format on save |
| GitHub Actions | `github.vscode-github-actions` | Workflow syntax and run status |
| Vim | `vscodevim.vim` | Vim keys in VS Code |

Extension versions update automatically. Pin one only if a version matters.

**A missing formatter extension gives no warning.** VS Code does not report
that a configured `defaultFormatter` is not installed. Format on save then
stops, and the files look correct until CI or a manual `ruff` run disagrees.
Settings Sync between devices can remove extensions this way, because the
device with the shorter list wins. If formatting does not run, examine the
extension list first and the settings second.

**Ruff in the editor is not the same tool as `ruff` in CI.** The extension
formats and shows diagnostics. The pinned `ruff` in `backend/requirements.txt`
is what CI runs. Their versions can differ, and only the second one can fail a
build.

**Prettier is pinned** as an exact devDependency in `frontend/package.json`.
The extension includes its own copy, but it prefers a copy in the workspace.
The pin keeps the editor and `npx prettier` on the same version. With two
versions, the editor and the command line format the same file differently.

Format on save is set for each language in `.vscode/settings.json`: Prettier
for TS, TSX, CSS and JSON, and Ruff for Python. Markdown is excluded, because
Prettier aligns every table in these documents again, which makes diffs
without a fix.

**Format on save is not lint on save.** `ruff format` changes only spaces and
line breaks. `ruff check` is a separate tool with its own rules, and
`editor.codeActionsOnSave` brings it to a save. Even then, it applies only the
fixes that ruff marks *safe*. `if x == None:` stays as written, because a
change to a comparison can change behavior. The editor's underline shows that
one, not the save. The two actions are `source.fixAll.ruff` and
`source.organizeImports.ruff`, not the forms without `.ruff`. Pylance also
answers `organizeImports` for Python, so the plain name does not say which
tool runs.

**Line endings are LF, set in two places, and both are necessary.** The
repository stores every text file with LF. Prettier's `endOfLine` is `lf`,
and Git's `core.autocrlf=true` writes CRLF on checkout, so a fresh clone fails
`npx prettier --check src/` without these two settings:

- `.gitattributes` (`* text=auto eol=lf`) controls the files that **Git**
  writes. It is committed, so it applies on every machine, whatever that
  machine's `core.autocrlf` is. `text=auto` still lets Git find binary files,
  so the audio fixtures under `backend/tests/fixtures/` do not change.
- `"files.eol": "\n"` in `.vscode/settings.json` controls the files that the
  **editor** creates, which no checkout rule sees. VS Code on Windows creates
  new files with `\r\n`, and format on save does not correct them: Prettier
  changes the content, and the editor writes the line endings.

## Git configuration (global)

```
user.name          = Curro
user.email         = 254643964+FranciscoJavierCurroAlcalaSoler@users.noreply.github.com
init.defaultBranch = main
core.editor        = code --wait
```

Credential helper: Git Credential Manager, set by the Git installer.

## Repository

| | |
|---|---|
| Remote | https://github.com/FranciscoJavierCurroAlcalaSoler/music-zamlr |

## Setup choices

- The Node installer option "Automatically install the necessary tools"
  (Tools for Native Modules) is not selected. Nothing in the project needs
  it. It runs a script that installs Chocolatey, a second Python, the legacy
  Python Launcher and Visual Studio Build Tools, and the launcher in
  `C:\Windows` then replaces the Python Install Manager's `py`.
- Python 3.14. The whole stack also supports 3.13.

## Not tracked here

Each of these has its own file. Do not copy their contents into this file:

- Python packages: `backend/requirements.txt`
- npm packages: `frontend/package.json` and `frontend/package-lock.json`

System programs have no lockfile, so the [Tools](#tools) table above records
them.

**Write `requirements.txt` as UTF-8.** Under Windows PowerShell 5.1, the
redirect in `pip freeze > requirements.txt` writes UTF-16. Git then classifies
the file as binary: it shows no diff, and it skips the line-ending rule. Tools
other than pip can also fail to read it. Redirect it like this:

```
pip freeze | Out-File -Encoding utf8 requirements.txt
```
