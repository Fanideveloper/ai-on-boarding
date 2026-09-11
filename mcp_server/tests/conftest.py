"""Put the server's modules on the import path.

`mcp_server/` is a standalone application rather than an installed package - it is run from
this directory, not imported by anything else - so its modules are imported by plain name.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
