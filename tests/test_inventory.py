"""Tests for Backend.list_installed (the inventory that keeps --scan and the
dashboard from ever showing a blank list) and for the display-category
taxonomy that powers the type filters."""
import subprocess

import archbooster.core.backends.flatpak as flatpak_mod
import archbooster.core.backends.pacman as pacman_mod
from archbooster.core.backends.flatpak import FlatpakBackend
from archbooster.core.backends.pacman import PacmanBackend
from archbooster.core.categorizer import categorize, display_category
from archbooster.core.scanner import Package


class _Result:
    def __init__(self, stdout):
        self.stdout = stdout
        self.returncode = 0


# ---- pacman inventory --------------------------------------------------- #

def test_pacman_list_installed_tags_foreign_packages_as_aur(monkeypatch):
    monkeypatch.setattr(pacman_mod.shutil, "which", lambda name: "/usr/bin/pacman")

    def fake_run(cmd, **kwargs):
        if cmd == ["pacman", "-Q"]:
            return _Result("firefox 128.0-1\nyay 12.3.5-1\nlinux 6.9.arch1-1\n")
        if cmd == ["pacman", "-Qqm"]:
            return _Result("yay\n")
        raise AssertionError(f"unexpected command {cmd}")

    monkeypatch.setattr(pacman_mod.subprocess, "run", fake_run)

    installed = PacmanBackend().list_installed()
    by_name = {p.name: p for p in installed}

    assert by_name["yay"].source == "AUR"
    assert by_name["firefox"].source == "official"
    assert all(p.status == "up-to-date" for p in installed)
    assert by_name["linux"].current == "6.9.arch1-1"
    assert by_name["linux"].new == by_name["linux"].current


def test_pacman_list_installed_empty_without_pacman(monkeypatch):
    monkeypatch.setattr(pacman_mod.shutil, "which", lambda name: None)
    assert PacmanBackend().list_installed() == []


def test_pacman_list_installed_survives_timeout(monkeypatch):
    monkeypatch.setattr(pacman_mod.shutil, "which", lambda name: "/usr/bin/pacman")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(pacman_mod.subprocess, "run", fake_run)
    assert PacmanBackend().list_installed() == []


# ---- flatpak inventory --------------------------------------------------- #

def test_flatpak_list_installed_parses_apps(monkeypatch):
    monkeypatch.setattr(flatpak_mod.shutil, "which", lambda name: "/usr/bin/flatpak")

    def fake_run(cmd, **kwargs):
        assert cmd == ["flatpak", "list", "--app", "--columns=application,version"]
        return _Result("org.gimp.GIMP\t2.10.38\ncom.spotify.Client\t\n")

    monkeypatch.setattr(flatpak_mod.subprocess, "run", fake_run)

    installed = FlatpakBackend().list_installed()
    by_name = {p.name: p for p in installed}

    assert by_name["org.gimp.GIMP"].current == "2.10.38"
    assert by_name["com.spotify.Client"].current == "?"   # blank version placeholder
    assert all(p.source == "Flatpak" and p.status == "up-to-date" for p in installed)


# ---- display categories --------------------------------------------------- #

def _categorized(name, source="official", gui=frozenset()):
    pkg = Package(name=name, current="1", new="2", source=source, priority="normal")
    categorize([pkg], gui_packages=gui)
    return pkg


def test_kernel_and_driver_split_out_of_critical():
    assert _categorized("linux").category == "kernel"
    assert _categorized("linux-lts").category == "kernel"
    assert _categorized("linux-firmware").category == "drivers"   # not kernel
    assert _categorized("nvidia-utils").category == "drivers"
    assert _categorized("mesa").category == "drivers"
    assert _categorized("intel-ucode").category == "drivers"
    assert _categorized("systemd").category == "system"
    assert _categorized("glibc").category == "system"


def test_fonts_and_themes_category():
    assert _categorized("ttf-dejavu").category == "fonts-themes"
    assert _categorized("papirus-icon-theme").category == "fonts-themes"


def test_gui_detection_splits_apps_from_cli():
    assert _categorized("firefox", gui=frozenset({"firefox"})).category == "apps"
    assert _categorized("ripgrep", gui=frozenset({"firefox"})).category == "cli"


def test_flatpak_and_snap_are_always_apps_brew_is_cli():
    assert _categorized("org.gimp.GIMP", source="Flatpak").category == "apps"
    assert _categorized("spotify", source="snap").category == "apps"
    assert _categorized("openssl", source="brew").category == "cli"


def test_display_category_never_consulted_for_safety():
    # The safety layer stays priority-based: a "drivers" category package is
    # still priority critical, which is what locks it out of the app update.
    pkg = _categorized("nvidia-utils")
    assert pkg.priority == "critical"
    assert display_category(pkg) == "drivers"
