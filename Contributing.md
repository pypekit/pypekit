# Contributing to **pypekit**

## Setup

1. Fork & clone this repo.
2. Install project + dev tools:
   ```bash
   pip install -e .[dev]
   ```
3. Check the installation:
   ```bash
   hatch run check
   ```

## Commits & PRs

* Follow conventional commits (`feat: …`, `fix: …`, `docs: …`).
* Run `hatch run fmt` to auto format your code.
* Run `hatch run check` locally — CI must be green.
* Open a pull request.
