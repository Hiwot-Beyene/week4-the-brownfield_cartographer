# week4-the-brownfield_cartographer

Brownfield Cartographer — Phase 1: Surveyor Agent (static structure analysis).

## Setup and run

1. **Use the project’s Python**  
   Activate your conda/venv so `python` is the environment’s interpreter (not system Python):

   ```bash
   conda activate week4-the-brownfield_cartographer
   which python   # should point into your env, not /usr/bin/python
   ```

2. **Install dependencies** (in that env):

   ```bash
   pip install -r requirements.txt
   ```

   Or install the project in editable mode (uses `pyproject.toml`):

   ```bash
   pip install -e .
   ```

3. **Run Phase 1 analysis** (from repo root):

   ```bash
   python -m src.cli analyze .
   ```

4. **Run tests**:

   ```bash
   python -m pytest -q
   ```

## Dependency files

- **`requirements.txt`** — Pinned deps for `pip install -r requirements.txt`. Use this for a reproducible install in any venv/conda env.
- **`pyproject.toml`** — Project metadata and dependencies; use `pip install -e .` for editable install.
- **`requirements.lock`** — Same pins as above; optional reference for lockfile-style installs.