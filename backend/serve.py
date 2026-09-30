"""The entry point the packaged app starts, in place of `fastapi dev`.

The shell that launches this process reads the port out of the first line
that carries PORT_LINE_PREFIX, so that no port has to be agreed in advance
and two copies of the app can never collide over one.

`app` is imported rather than named as the string "main:app". PyInstaller
follows imports and cannot see a module inside a string, so the string form
builds a binary that starts and then fails to find its own application.
"""

import logging
import os
import socket
import sys
import threading
from logging.handlers import RotatingFileHandler

from uvicorn import Config, Server

from database import DB_PATH
from launch_settings import read_launch_settings
from main import app

PORT_LINE_PREFIX = "ZAMLR_PORT="
LOG_LINE_PREFIX = "ZAMLR_LOG="
LOG_FILE_NAME = "music-zamlr.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
MAX_LOG_BYTES = 1024 * 1024
LOG_FILES_KEPT = 3
# A shutdown waits for open connections, and four endpoints here hold one for
# the length of a scan or an import. When the shell is already gone there is
# nobody left to finish them for, so the wait is bounded.
SHUTDOWN_TIMEOUT_SECONDS = 5


def configure_file_logging(log_directory: str) -> str:
    """Send every log record to a file in log_directory, and say where.

    The argument is a directory, not a file: the name inside it is this
    application's to choose, and the shell only knows where app-data is.

    Rotation is here because nobody visits the machine this runs on. A diff
    over a large collection can write a warning per unreadable file.
    """
    os.makedirs(log_directory, exist_ok=True)
    log_path = os.path.join(log_directory, LOG_FILE_NAME)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_FILES_KEPT,
        # utf-8, or the file is written in the machine's code page and a
        # record naming a Japanese or Cyrillic path raises inside the
        # logging call. A music library is full of such paths.
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger = logging.getLogger()
    # The file replaces every other handler rather than joining them.
    # scanner.py calls logging.basicConfig at import, which leaves a handler
    # writing to the console, and this process has no console: its stdout is
    # a pipe the shell reads for the announcements above. A running server
    # logs a line per request, and a pipe nobody drains fills and then
    # blocks the process that writes to it.
    for existing in list(root_logger.handlers):
        root_logger.removeHandler(existing)
    root_logger.addHandler(handler)
    # The root logger starts at WARNING, and a record is dropped by the
    # level of the logger it was made on before any handler sees it. Without
    # this, every INFO line made on a logger of our own would be lost.
    # scanner.py's basicConfig happens to raise the root level already, so
    # this looks redundant today and is not: it states what this function
    # needs rather than inheriting it from another module's import.
    root_logger.setLevel(logging.INFO)
    return log_path


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


def exit_when_input_closes(server: Server) -> threading.Thread:
    """Stop the server once the pipe from the shell closes.

    The shell stops this process when the app closes normally. Nothing runs
    when the shell crashes, and an orphan holds the port, the database and
    the log file, so the next launch looks like a broken installation. The
    pipe closes however the parent dies, which is the one signal that
    arrives in every case.

    One byte, because nothing is ever sent on this pipe: only its closing
    carries meaning. A daemon thread, because a plain thread blocked on a
    read would keep the interpreter alive after the server had stopped.

    should_exit is set rather than the process being ended here. Uvicorn
    polls that flag and runs its own shutdown, which is what leaves the
    database whole.
    """

    def wait_for_end_of_input():
        sys.stdin.buffer.read(1)
        server.should_exit = True

    watcher = threading.Thread(target=wait_for_end_of_input, daemon=True)
    watcher.start()
    return watcher


def port_line(port):
    return f"{PORT_LINE_PREFIX}{port}"


def log_line(log_path):
    return f"{LOG_LINE_PREFIX}{log_path}"


def main():
    # Through the settings rather than os.environ directly, so that the
    # directory is held to the same rules as every other configured path.
    launch_settings = read_launch_settings(os.environ)
    log_path = None
    if launch_settings.log_directory:
        log_path = configure_file_logging(launch_settings.log_directory)

    server_socket = bind_local_socket()
    port = server_socket.getsockname()[1]
    # flush, because Python writes to a pipe in blocks rather than in lines.
    # A terminal would show this at once; a pipe holds it until several
    # kilobytes have built up, and the shell waits for a port that is sitting
    # in a buffer while a perfectly healthy backend serves nobody.
    print(port_line(port), flush=True)
    # After the port, never before it, so that a reader which takes the first
    # line still finds what it came for. The shell needs this to show the
    # user their log, and taking it from here rather than composing it from
    # LOG_FILE_NAME keeps the name this application's own business.
    if log_path is not None:
        print(log_line(log_path), flush=True)

    # DB_PATH rather than the variable, because it is the path actually in
    # use: the variable is absent whenever the fallback applies. The token is
    # never logged — this file is what a user will be asked to send on.
    logging.getLogger(__name__).info(
        "Backend starting on port %s with database %s", port, DB_PATH
    )

    config = Config(
        app=app,
        host="127.0.0.1",
        port=port,
        reload=False,
        log_config=None,
        timeout_graceful_shutdown=SHUTDOWN_TIMEOUT_SECONDS,
    )
    server = Server(config)
    # Only when the shell asks. A process started with no input at all sees
    # the end of it at once, so a watcher nobody asked for would stop the
    # server as it started. The flag is the shell's word that it opened a
    # pipe on the other side.
    if launch_settings.watch_stdin:
        exit_when_input_closes(server)
    server.run(sockets=[server_socket])


if __name__ == "__main__":
    main()
