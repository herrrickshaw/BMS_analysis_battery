# vcrud/ — extracted, NOT activated

This module was extracted from a stray `working-files` repo during a 2026-07-17
repo hygiene pass. It is **not imported or wired into `main.py`** and
`backend/routers/vcrud_router.py` is **not registered** as a router.

Prior-session memory flags vCRUD's "mandatory workflow" as a git-hijacking
hazard — it auto-commits and switches branches on its own. Review
`vcrud_manager.py` / `vcrud_cli.py` yourself before activating any of this;
do not wire it into the app without understanding that behavior first.
