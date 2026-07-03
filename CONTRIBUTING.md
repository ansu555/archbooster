# Contributing to ArchBooster

Thanks for considering it. Before diving in, read the section below —
it'll save you from writing a PR that doesn't fit where this project actually
is right now.

## Where this project is, honestly

ArchBooster hit its v0.2 milestone with everything on the original roadmap
shipped: unification across pacman/AUR/Flatpak/apt/dnf/Snap/Homebrew, the
app-vs-system guardrail, changelog viewing, snapshot/rollback, and update
profiles. There is **no active roadmap of new features** — this isn't a
"we'll get to it" gap, it's genuinely feature-complete for what it set out to
do. So don't expect a backlog of "help wanted" issues to pick from.

That said, there's real, useful work available:

### 1. Real-world testing on distros/backends the maintainer can't run

The apt, dnf, and Snap backends were built and unit-tested against **mocked**
`subprocess`/`shutil.which` output on an Arch dev machine — none of them have
been live-tested against a real Debian, Fedora, or snapd install. If you run
one of those and hit a parsing bug (a version string format that doesn't
match, a locale that changes command output, etc.), that's a genuine bug fix
with real value. File an issue with the exact command output first if you're
not sure it's fixable in a quick PR.

### 2. New backend ports

`archbooster/core/backends/base.py` defines the `Backend` ABC — the seam that
lets the app support a new package manager without touching the UI. Look at
`backends/apt.py` or `backends/dnf.py` as templates (parse a list command's
output into `Package` objects, enforce a per-backend system-layer pattern
list in `categorizer.py`). Plausible candidates nobody's built yet:

- `zypper` (openSUSE)
- `apk` (Alpine)
- `xbps` (Void)
- Portage/`emerge` (Gentoo)

Each is a self-contained PR: one new `backends/<name>.py`, a registry entry,
and tests mocking that package manager's real CLI output (see
`tests/test_apt.py` / `tests/test_dnf.py` for the pattern).

### 3. AUR publishing

`packaging/aur/{archbooster,archbooster-bin}/` has ready PKGBUILDs, but
`aur.archlinux.org` currently has new-account registration closed, so nobody
has pushed them yet. If you already have an AUR account, see
`packaging/aur/README.md` for the remaining steps (`updpkgsums`, regenerate
`.SRCINFO`, push to the AUR git remote) and open a PR/issue to coordinate.

### 4. Bug fixes, docs, and edge cases

Normal open-source stuff: if something breaks, a doc is stale, or a test
gap is real, that's always welcome — no need to check with anyone first for
something this scoped.

**Not currently in scope:** new top-level features beyond backend coverage
(the "unify updates + guardrail" identity is deliberately the whole point —
see the README's "Why this" section before proposing something adjacent).
If you have an idea that doesn't fit the categories above, open an issue to
discuss it before writing code.

## Dev setup

```bash
git clone https://github.com/ansu555/archbooster
cd archbooster
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest -q
```

192 tests should pass in a few seconds. CI (`.github/workflows/ci.yml`) runs
the same command against Python 3.11, 3.12, and 3.13 on every PR.

## Making a change

1. Fork the repo and branch off `main`.
2. Keep PRs scoped to one backend/fix/doc change — small and reviewable
   beats a bundle of unrelated changes.
3. Add or update tests for any behavior change. Backend PRs should mock the
   underlying CLI's real output rather than hitting the actual package
   manager (see any file under `tests/` for the pattern) — this is what lets
   CI verify a Debian/Fedora/Alpine backend from an Arch runner.
4. There's no enforced linter/formatter yet — just match the style of the
   surrounding file.
5. Run `pytest -q` locally before opening the PR.
6. Open the PR against `main` and describe *what* changed and *why* — the
   existing code's docstrings/comments explain non-obvious tradeoffs
   (see `core/backends/base.py` for the tone to match).

## Reporting bugs

Open an issue with:

- Your distro and version
- Which backend is involved (pacman/AUR/Flatpak/apt/dnf/Snap/Homebrew)
- `archbooster --version` (or the git commit if running from source)
- The actual command output, if it's a parsing issue

## License

By contributing, you agree your contribution is licensed under this
project's [MIT license](LICENSE).
