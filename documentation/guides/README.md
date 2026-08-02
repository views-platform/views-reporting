# Guides

Practical, copy-paste runbooks for operational tasks (the "how do I actually do X" docs). Unlike ADRs (decisions) and CICs (class contracts), guides are step-by-step procedures meant to be followed cold.

- [**Publishing to PyPI**](publishing-to-pypi.md) — test deployment (TestPyPI rehearsal), first real deployment, and the repeatable update loop. Pins this repo's release gotchas (declared Python envelope `>=3.11,<3.15` but 3.11 tested-on/practically-installable — C-36; uv+hatchling; write-once versions).
