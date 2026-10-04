# Contributing to Music Zamlr

This file is for people who run Music Zamlr from its source code, change it,
or build a release. To install the Windows program, read the
[README](README.md#install).

## Contributions

Music Zamlr is a personal project, and I write its code myself. Bug reports
and questions are welcome as issues. I do not accept pull requests that add
features. If you want to fix a bug, open an issue first. I can decline any
pull request.

## Running from source

These steps work on Windows, Linux, and macOS. On Linux and macOS, this is the
way to use the program.

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
is more than ten years old. The automated tests and the Windows installer use
the version that `FPCALC_VERSION` names in `.github/workflows/ci.yml`.

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
database of an installed Windows program, which is in
`%APPDATA%\com.zamlr.music`.

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

## Making a release

1. Change `version` in `frontend/src-tauri/tauri.conf.json`. The installer
   gets its version only from this file. Commit and push.
2. Push a tag with the same version:

   ```
   git tag v0.2.0
   git push origin v0.2.0
   ```

3. The release workflow builds the installer and makes a draft release. The
   draft has four files: the installer, the Python source archive, the
   `fpcalc` source archive, and `THIRD-PARTY-NOTICES.txt`. The workflow stops
   if the tag and the version are different.
4. Wait until the CI workflow for the same tag passes. The release workflow
   cannot wait for it.
5. Download the installer from the draft with a browser, install it, and start
   the program. A file that you download with a browser shows the SmartScreen
   dialog that users see.
6. Publish the draft.

Do not publish a draft that does not have all four files. The backend program
is under the GPL, and `fpcalc` is under the LGPL. Both licenses need the source
code and the license texts next to the program.

If you change `FPCALC_VERSION`, the workflow stops at the `fpcalc` sources. The
source files and their hashes in `.github/workflows/release.yml` belong to one
version. Find the sources of the new version and change them too.

If a workflow run fails, delete the draft and the tag before you push the tag
again:

```
gh release delete v0.2.0 --yes
git push --delete origin v0.2.0
git tag -d v0.2.0
```
