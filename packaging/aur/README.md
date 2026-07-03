# AUR packaging

Two packages, published as separate AUR git repos (`ssh://aur@aur.archlinux.org/<pkgname>.git`):

- `archbooster/` — builds from the tagged source tarball (`python -m build --wheel`).
- `archbooster-bin/` — installs the prebuilt `archbooster-linux-x86_64` binary that
  the release workflow (`.github/workflows/release.yml`) attaches to each GitHub
  Release tagged `vX.Y.Z`.

## Cutting a new version

After tagging `vX.Y.Z` and letting the release workflow publish the GitHub Release:

```sh
cd packaging/aur/archbooster
sed -i "s/^pkgver=.*/pkgver=X.Y.Z/" PKGBUILD
updpkgsums
makepkg --printsrcinfo > .SRCINFO

cd ../archbooster-bin
sed -i "s/^pkgver=.*/pkgver=X.Y.Z/" PKGBUILD
updpkgsums
makepkg --printsrcinfo > .SRCINFO
```

Then push each `PKGBUILD` + `.SRCINFO` pair to its AUR git repo.
