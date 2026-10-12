# Security policy

## Supported versions

Only the newest release on the
[Releases page](https://github.com/FranciscoJavierCurroAlcalaSoler/music-zamlr/releases)
gets security fixes. A fix comes in a new release. Older releases do not get
fixes.

## Report a security problem

Do not open a public issue for a security problem. Report it privately:

1. Open the
   [Security tab](https://github.com/FranciscoJavierCurroAlcalaSoler/music-zamlr/security)
   of this repository.
2. Select **Report a vulnerability**.
3. Write what an attacker can do, the steps that show it, and the version
   and the system that you used.

Only you and I can read the report. I will answer within 14 days. When a fix
is released, I will publish the report as an advisory. If you want, the
advisory gives your name.

## What a security problem is here

Music Zamlr runs only on your computer. The backend program accepts
connections only from the same computer. In the desktop program, each request
must also have a token. The window makes a new token each time that it starts
the backend. These are examples of security problems:

- Another program or a web page sends a request that the backend accepts.
- An import writes, moves, or deletes a file outside the folders that you
  selected.
- A crafted audio file or folder name makes the backend run code.

A problem that needs an attacker who already controls your user account is
not a security problem for this project. Report it as a bug.
