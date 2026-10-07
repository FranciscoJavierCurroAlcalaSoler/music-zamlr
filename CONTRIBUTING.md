# Contributing to Music Zamlr

This file is for people who run Music Zamlr from its source code, change it,
or build a release. To install the program on Windows or Linux, read the
[README](README.md#install).

## Contributions

Music Zamlr is a personal project, and I write its code myself. Bug reports
and questions are welcome as issues. I do not accept pull requests that add
features. If you want to fix a bug, open an issue first. I can decline any
pull request.

## Running from source

These steps work on Windows, Linux, and macOS. On macOS, this is the way to
use the program.

You need:

- Python 3.14
- Node.js 24
- `fpcalc`, the command-line program of Chromaprint. The program uses it to
  compare the sound of two files. Without it, the program compares tags only
  and shows a warning.

### 1. Install the backend

Clone the repository. Then, on Windows:

```
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On Linux and macOS:

```
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Install the interface

```
cd frontend
npm install
```

### 3. Install fpcalc

Use the package manager of your system:

```
winget install --id AcoustID.Chromaprint --exact    # Windows
brew install chromaprint                            # macOS
sudo apt install libchromaprint-tools               # Debian and Ubuntu
```

On Windows, do not use the Chocolatey package. It installs version 1.1, which
is more than ten years old. The automated tests, the installer and the Linux
package use the version that `FPCALC_VERSION` names in
`.github/workflows/ci.yml`. apt and Homebrew can have a different version.

Open a new terminal. Then make sure that this command shows a version:

```
fpcalc -version
```

A terminal that was open before the installation does not find `fpcalc`. For
the same reason, start the backend in a new terminal.

### 4. Start the program

Open two terminals. Start the backend in the first one, with its virtual
environment active:

```
cd backend
fastapi dev main.py
```

Start the interface in the second one:

```
cd frontend
npm run dev
```

Then open `http://localhost:5173` in a browser. The backend answers on port
8000, and the interface expects it there.

In a browser, the folder fields have no **Browse…** button, because a browser
cannot open a folder picker on the computer that runs the backend. Type the
path of each folder.

When you run from source, the database is `backend/db/music.db`. It is not the
database of an installed program, which is in `%APPDATA%\com.zamlr.music` on
Windows and in `~/.local/share/com.zamlr.music` on Linux.

## Building the Windows installer

A local installer is for a test only. Releases come from the release workflow,
which runs when a version tag is pushed. A local installer has no
`THIRD-PARTY-NOTICES.txt` and no source archives, so do not distribute it.

You need everything in [Running from source](#running-from-source), and also:

- Rust, installed with rustup, on the `stable-x86_64-pc-windows-msvc`
  toolchain.
- Visual Studio 2022 Build Tools with the C++ workload. Rust links through
  them. The MSVC tools install before the Windows SDK, and linking fails until
  both are there.
- `fpcalc.exe` in `frontend/src-tauri/binaries/`. Copy it there one time,
  from the version that `FPCALC_VERSION` names. That folder is not in git.

Then, from the repository:

```
cd backend
pyinstaller music-zamlr-backend.spec --noconfirm
python stage_backend.py
cd ../frontend
npm run tauri build
```

The installer is in `frontend/src-tauri/target/release/bundle/nsis/`.

`stage_backend.py` copies the new backend build into
`frontend/src-tauri/binaries/`. Run it after each PyInstaller build. The
installer contains whatever is in that folder and does not examine it, so an
old copy goes into the installer without a warning.

### An antivirus program can stop the Rust build

If each Rust build fails with
`LINK : fatal error LNK1105: cannot close file ... error code 1224`, an
on-access virus scanner opens the files that the linker writes. Add
`frontend/src-tauri/target` to the exclusions of that scanner. Windows Defender
does not cause this error. The error occurred with FortiClient.

## Building the Linux package

A local package is for a test only, for the same reasons as a local
installer. To get a package from the same steps as a release, run the Linux
workflow on GitHub and download its artifact:

```
gh workflow run linux-package.yml
```

To build on your own computer, you need a Debian-based system and everything
in [Running from source](#running-from-source), and also:

- Rust, installed with rustup, on the stable toolchain.
- The libraries that Tauri builds against:

  ```
  sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
  ```

- `fpcalc` in `frontend/src-tauri/binaries/`, from the Linux archive of the
  version that `FPCALC_VERSION` names. Copy it there one time, and keep its
  execute permission.

Then, from the repository:

```
cd backend
pyinstaller music-zamlr-backend.spec --noconfirm
python stage_backend.py
cd ../frontend
npm run tauri build
```

The package is in `frontend/src-tauri/target/release/bundle/deb/`.
`tauri.linux.conf.json` makes the build produce a `.deb` and name the program
`music-zamlr`.

A program built on a system runs only on systems with the same C library or a
newer one. The workflow builds on Ubuntu 22.04 for that reason. A package
that you build on a newer system does not install on an older one.

## How the code is organized

- `backend/` is the FastAPI backend. `main.py` holds the endpoints.
  `matching.py`, `fingerprinting.py`, `importing.py`, and `hashing.py` hold the
  logic. `models.py` holds the database tables, and `schemas.py` holds the
  API contract.
- `frontend/` is the React interface. `frontend/src-tauri/` is the desktop
  window.

### Rules for the backend

- `matching.py`, `importing.py`, `fingerprinting.py`, and `hashing.py` do not
  use the database and do not import FastAPI. Their tests use plain objects in
  memory.
- `enums.py` imports nothing from this project, so the logic modules and the
  API contract can both use it.
- `schemas.py` is the API contract. The logic modules never import it.
- Facts about the computer go into the logic as parameters. The planner gets
  `path_exists` and does not call `os.path.exists`. The matcher gets
  `fingerprints_available` and does not search `PATH`. A module that examines
  the computer itself passes or fails its tests according to the computer.
- The matcher stores the hashes and fingerprints that it calculates on the
  track objects. The endpoint that called the matcher writes them to the
  database.
- Every file path goes through `os.path.normpath()`. Do not make a path with
  `/` or `\` by hand.
- Two kinds of path comparison exist. When the question is "can these two paths
  collide on disk", compare them with `casefold()`, because Windows ignores
  letter case. The import planner and the `_superseded` folder use this. When
  the question is "which row is this file", compare them exactly. The scanner
  uses this, so that two files whose names differ only in letter case on Linux
  stay two rows.
- Compare enum values with `==`, not `is`, so that a string from a request
  body is equal to its enum value.
- Never overwrite a file without a sign, and never decide an uncertain match.
  An uncertain match goes to the user. A destination that collides gets a
  numbered suffix. A file is deleted only after its replacement is written.
- If an error means "the filesystem refused", catch it and report it for that
  one operation. If an error means "this code has a bug", let it go up.
- A change to a table needs an Alembic revision. See
  [Changing the database](#changing-the-database).

### Comments

A comment tells why the code is as it is, mainly where a simpler version looks
correct and is not. It does not repeat what the code says, and it does not
tell the history of a change.

## Tests

Backend, from `backend/` with the virtual environment active:

```
python -m pytest
ruff check .
ruff format --check .
```

Use `python -m pytest`, not `pytest`. The `-m` form adds the current folder to
the import path. Without it, the tests cannot import the backend modules.

Interface, from `frontend/`:

```
npm run typecheck
npm run lint
npx prettier --check src/
npm test
```

Use `npm run typecheck`, never `npx tsc --noEmit`. The root `tsconfig.json`
has `"files": []` and passes the work to project references. `tsc --noEmit`
therefore examines no files and always passes. `tsc -b`, which
`npm run typecheck` runs, follows the references.

### Rules for tests

- Compare relations, not literal ids. Make expected paths with
  `os.path.normpath`, so that the tests pass on Linux as well as on Windows.
- Shared test factories are fixtures in `backend/tests/conftest.py`. Test
  modules do not import from each other.
- Do not compare the text of an operating-system error. Windows translates
  it into the language of the computer.
- For an endpoint that streams its result, examine the `done` frame. Such an
  endpoint always answers 200, also when its body is an error frame.
- `backend/tests/test_packaged_backend.py` runs only when `backend/dist/`
  holds a PyInstaller build. If any `.py` file in `backend/` is newer than the
  build, these tests fail and tell you to build again.

### Changing the database

When you change a model in `backend/models.py`, write an Alembic revision.
`test_the_migrations_match_the_models` fails until the revision exists.

Generate the revision against an empty database, not against your own. Alembic
compares the models with the database that it connects to, and your own
database can already have the change. From `backend/`, on Windows:

```
$env:ZAMLR_DATABASE_PATH = "<absolute path to a new, empty .db file>"
alembic revision --autogenerate -m "<what changed>"
Remove-Item env:ZAMLR_DATABASE_PATH
```

Read the revision before you commit it. A revision that changes or removes a
column uses batch mode, because SQLite cannot change a column in place. Batch
mode copies the table, so foreign keys must be off while the revision runs.
`PRAGMA foreign_keys` has no effect inside a transaction. Set it before the
transaction starts, and read it back to make sure that it changed.

## Changing the app icon

Two drawings in `frontend/src-tauri/` make the icon. `app-icon-small.svg`
makes the 16 px, 24 px and 32 px images in `icon.ico`. At these sizes, the Z
in `app-icon.svg` is too small to read. Windows shows the 32 px image in the
title bar and on the taskbar. `app-icon.svg` makes all the other images.

Do the steps in this sequence. `tauri icon` makes all the images in
`icon.ico` from one drawing. If you do step 1 last, the small images become
unreadable again. From `frontend/`:

1. Make all the images from the full drawing:

   ```
   npm run tauri icon src-tauri/app-icon.svg
   ```

2. The command also writes images that this project does not use, for
   example `icons/android/` and `icons/ios/`. Delete the new files that
   `git status` shows as untracked.
3. Make the three small images in a temporary folder:

   ```
   npm run tauri icon src-tauri/app-icon-small.svg -- -p 16,24,32 -o <temporary folder>
   ```

4. Put the three small images into `icon.ico`. The script needs Python 3.9 or
   later and no other package:

   ```
   python ../backend/replace_small_icons.py <temporary folder>
   ```

5. If you use `npm run tauri dev`, give `tauri.conf.json` a new time. The
   build script runs again only when `tauri.conf.json`, `capabilities/` or
   `binaries/` changes, so without this step the program keeps the old
   icon. In PowerShell:

   ```
   (Get-Item src-tauri\tauri.conf.json).LastWriteTime = Get-Date
   ```

## Making a release

1. Change `version` in `frontend/src-tauri/tauri.conf.json`. The installer and
   the package get their version only from this file. Commit and push.
2. Push a tag with the same version:

   ```
   git tag v0.2.0
   git push origin v0.2.0
   ```

3. The release workflow builds the Windows installer and the Linux package,
   and then makes a draft release with eight files. For each system, these are
   the program, the Python source archive, the `fpcalc` source archive, and
   `THIRD-PARTY-NOTICES.txt`. The workflow makes no draft if either build
   fails, and it stops if the tag and the version are different.
4. Wait until the CI workflow for the same tag passes. The release workflow
   cannot wait for it.
5. Download the installer from the draft with a browser. Install it over the
   previous version, start the program, and make sure that your collections
   are still there. A file that you download with a browser shows the
   SmartScreen dialog that users see.
6. Install the package from the draft on a Linux system, and start the
   program from the applications menu.
7. Publish the draft.

Each backend program is under the GPL, and each `fpcalc` is under the LGPL.
Both licenses need the source code and the license texts next to the program,
so the workflow does not make a draft that has fewer than eight files.

To test a change to the release workflow without a tag, run it by hand. Every
job runs except the one that makes the draft:

```
gh workflow run release.yml
```

If you change `FPCALC_VERSION`, the workflow stops at the `fpcalc` sources. The
source files and their hashes in `backend/collect_fpcalc_sources.py` belong to
one version. Find the sources of the new version and change them too.

Compiled code in a Python package can contain code from other projects, and
the notices must name that code. `backend/check_compiled_packages.py` keeps a
list of the compiled packages in the program, each at the version that a
person examined. If you change the version of a package in this list, a test
fails in CI. If a package with compiled code that is not in the list goes into
the program, the build workflows stop after PyInstaller. Find what the package
compiles in (for example, the Rust crates in its source archive). Make sure
that `THIRD-PARTY-NOTICES.txt` includes it. Then change `AUDITED_COMPILED`.

If a workflow run fails, delete the draft and the tag before you push the tag
again:

```
gh release delete v0.2.0 --yes
git push --delete origin v0.2.0
git tag -d v0.2.0
```
