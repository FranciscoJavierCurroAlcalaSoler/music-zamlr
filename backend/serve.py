"""The entry point the packaged app starts, in place of `fastapi dev`.

The shell that launches this process reads the port out of the first line
that carries PORT_LINE_PREFIX, so that no port has to be agreed in advance
and two copies of the app can never collide over one.

`app` is imported rather than named as the string "main:app". PyInstaller
follows imports and cannot see a module inside a string, so the string form
builds a binary that starts and then fails to find its own application.
"""

import socket

from uvicorn import Config, Server

from main import app

PORT_LINE_PREFIX = "ZAMLR_PORT="


def bind_local_socket():
    """Listen on a port the operating system picks, on the loopback only.

    Port 0 asks for any free port, which is what keeps two copies of the app,
    or a development backend already on 8000, from colliding.

    It listens here rather than inside uvicorn so that the port exists before
    it is announced. A connection that arrives between the announcement and
    uvicorn's first accept then waits in the backlog, instead of being
    refused and having to be read as "not started yet".
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("127.0.0.1", 0))
    server_socket.listen()
    return server_socket


def port_line(port):
    return f"{PORT_LINE_PREFIX}{port}"


def main():
    server_socket = bind_local_socket()
    port = server_socket.getsockname()[1]
    # flush, because Python writes to a pipe in blocks rather than in lines.
    # A terminal would show this at once; a pipe holds it until several
    # kilobytes have built up, and the shell waits for a port that is sitting
    # in a buffer while a perfectly healthy backend serves nobody.
    print(port_line(port), flush=True)

    config = Config(app=app, host="127.0.0.1", port=port, reload=False)
    Server(config).run(sockets=[server_socket])


if __name__ == "__main__":
    main()
