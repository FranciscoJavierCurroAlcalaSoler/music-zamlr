"""What Alembic runs before every migration.

The engine comes from `database`, never from a `sqlalchemy.url` in
`alembic.ini`. The packaged app is told its database path at launch, so a
URL written here would be right on the machine that wrote it and wrong on
every machine that installs the app.

No `fileConfig` call, although the template has one and `alembic.ini` still
carries the `[loggers]` sections it reads. Migrations run inside the app,
and reconfiguring the root logger from that file would throw away the
handlers the backend installed to write its log.

No offline mode either. It emits SQL for somebody to run by hand against a
database this code cannot reach, and there is no such database.
"""

from sqlmodel import SQLModel

import models  # noqa: F401 -- import defines and registers tables in SQLModel.metadata
from alembic import context
from database import engine

config = context.config

target_metadata = SQLModel.metadata


def run_migrations(connection) -> None:
    # render_as_batch because the database is SQLite, whose ALTER TABLE
    # cannot drop or alter a column. Batch mode copies the table into a new
    # one instead. Set for every revision, not only for the ones that need
    # it: a revision written without it is never tried under batch rules.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# A caller that passes its own connection keeps it: the test migrates an
# in-memory database and then inspects it through the same connection, which
# a `with` block here would have closed first. Opening one from the engine is
# the path the app and the command line take, and there the connection is
# ours to close.
connection = config.attributes.get("connection")
if connection is None:
    with engine.connect() as connection:
        run_migrations(connection)
else:
    run_migrations(connection)
