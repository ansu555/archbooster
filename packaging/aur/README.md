# AUR packaging

Two packages, each published as its own AUR git repo
(`ssh://aur@aur.archlinux.org/<pkgname>.git`):

- `archbooster/` — builds from the tagged source tarball (`python -m build --wheel`).
  **This is the one that is published.** `arch=any`, depends on Arch's
  `python-textual`, runs the test suite in `check()`.
- `archbooster-bin/` — installs the prebuilt `archbooster-linux-x86_64` binary that
  the release workflow (`.github/workflows/release.yml`) attaches to each GitHub
  Release. Kept ready but not currently published: a second AUR repo doubles the
  per-release work, and a package that builds in seconds does not need a `-bin`.

## First-time setup (once per maintainer machine)

1. Create an account at https://aur.archlinux.org and add an SSH public key
   under *My Account → SSH Public Key*.
2. Point SSH at it:

   ```sh
   cat >> ~/.ssh/config <<'EOF'
   Host aur.archlinux.org
     User aur
     IdentityFile ~/.ssh/aur
   EOF
   ```

3. Verify — this must print a greeting, not `Permission denied`:

   ```sh
   ssh aur@aur.archlinux.org help
   ```

4. `sudo pacman -S --needed base-devel pacman-contrib namcap`
   (`updpkgsums` and `namcap` live in `pacman-contrib` / `namcap`.)

## Cutting a release

Do these in order. Steps 1–3 happen in this repo; step 4 in the AUR clone.

**1. Bump the version.** `pyproject.toml` and both `PKGBUILD`s must agree:

```sh
V=X.Y.Z
sed -i "s/^version         = .*/version         = \"$V\"/" pyproject.toml
sed -i "s/^pkgver=.*/pkgver=$V/" packaging/aur/*/PKGBUILD
```

Reset `pkgrel=1` whenever `pkgver` changes. Bump `pkgrel` instead (leaving
`pkgver` alone) when only the packaging changed and upstream did not.

**2. Tag and let CI publish the GitHub Release.** The checksums in step 3 are
taken from those artifacts, so the release must exist first:

```sh
git commit -am "Bump version to $V"
git tag "v$V" && git push origin main "v$V"
gh run watch          # wait for .github/workflows/release.yml
```

**3. Regenerate checksums and `.SRCINFO`.**

```sh
cd packaging/aur/archbooster
updpkgsums                          # NOT optional — see below
makepkg --printsrcinfo > .SRCINFO
makepkg -C --cleanbuild             # must build, test and package cleanly
namcap PKGBUILD *.pkg.tar.zst       # must be quiet
```

`updpkgsums` is the step that is easy to skip and must not be. `sha256sums=SKIP`
is legal to `makepkg` but means the tarball is installed with **no integrity
check at all** — a compromised or truncated download is accepted silently.
`SKIP` is only defensible for VCS sources, which these are not. Real sums are
also the first thing an AUR reviewer looks for.

**4. Push to the AUR.** The AUR repo holds *only* `PKGBUILD` and `.SRCINFO` —
never the whole project tree, and never `.pkg.tar.zst` or `src/`:

```sh
git clone ssh://aur@aur.archlinux.org/archbooster.git /tmp/aur-archbooster
cp packaging/aur/archbooster/{PKGBUILD,.SRCINFO,archbooster.service} /tmp/aur-archbooster/
cd /tmp/aur-archbooster
git add -A && git commit -m "Update to $V" && git push
```

For the very first push the clone is empty and git warns about cloning an empty
repository — that is expected; commit and push as above.

## Verifying before you push

`makepkg` in the checkout uses your installed packages, which can hide a missing
`depends`. A clean chroot uses only what the `PKGBUILD` declares:

```sh
sudo pacman -S --needed devtools
extra-x86_64-build          # builds in a throwaway chroot
```

If it builds there, it builds on a stranger's machine.

## Package notes

- `arch=any` — pure Python, no compiled extension.
- `depends=('python' 'python-textual')` — `python-textual` is in `extra`, so no
  vendored dependency and nothing pulled from PyPI at build time.
- `check()` runs the full suite. It is hermetic (see `tests/conftest.py`: the
  autouse fixture stubs the inventory and `.desktop` lookups), so it makes no
  network calls and shells out to no package manager — safe inside a chroot.
- `pacman-contrib` is an `optdepends`, not a `depends`: without `checkupdates`
  the scanner falls back to the local sync database (see
  `archbooster/core/scanner.py`), which works but can lag a sync behind.
- The repo's own `systemd/archbooster.service` points `ExecStart` at
  `%h/.local/bin` (the pipx path). A pacman install lands the entry point in
  `/usr/bin`, so this directory ships its own unit file instead.
