# Publishing to PyPI

Releases are published by GitHub Actions (`.github/workflows/publish.yml`) using PyPI
**trusted publishing**, so no PyPI password or token is stored anywhere.

## One-time setup

1. Sign in at <https://pypi.org> (create an account and turn on two-factor authentication if needed).
2. Go to **Your account > Publishing > Add a new pending publisher** and fill in:
   - PyPI project name: `town-hall-connector`
   - Owner: `Collert`
   - Repository name: `Town-hall-connector`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. On GitHub, open the repository's **Settings > Environments**, create an environment named `pypi`
   (optionally add yourself as a required reviewer, so every release waits for your click).

## Each release

1. Bump `__version__` in `src/townhall_connector/__init__.py` and add a section to `CHANGELOG.md`.
2. Merge to `main`.
3. On GitHub, **Releases > Draft a new release**, create a tag like `v0.1.0`, and publish it.
4. The **Publish to PyPI** workflow builds and uploads the package. A minute later
   `pip install town-hall-connector` installs the new version.

## Publishing by hand instead

```bash
pip install build twine
python -m build
twine upload dist/*        # username __token__, password: a PyPI API token
```
