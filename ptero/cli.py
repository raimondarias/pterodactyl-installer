"""Language selection, grouped maintenance menu and process locking."""
import argparse
import fcntl
import os
import sys

from . import __version__
from .i18n import LANGUAGES
from .ui import UI


def select_language(ui):
    if not ui.screen:
        ui.say("Language")
    language = ui.choice("Which language would you like to use?", [
        ("en", "English", ""), ("es", "Español", ""), ("pt-BR", "Português (Brasil)", "")],
        default=list(LANGUAGES).index(ui.language))
    ui.set_language(language)
    return language


ENTRIES = [
    ("Install Panel and Wings", "install-all"), ("Install Panel", "install-panel"),
    ("Install Wings", "install-wings"), ("Uninstall Panel and Wings", "uninstall-all"),
    ("Uninstall Panel", "uninstall-panel"), ("Uninstall Wings", "uninstall-wings"),
    ("Update Panel v2", "update-panel"), ("Update Wings", "update-wings"),
    ("Configure / link Wings", "configure-wings"), ("Wings HTTPS certificate", "tls-wings"),
    ("Back up Panel", "backup-panel"), ("Back up Wings configuration", "backup-wings"),
    ("Restore Panel from backup", "restore-panel"), ("Status and diagnostics", "diagnose"),
    ("Restart services", "restart"), ("View logs", "logs"), ("Configure SMTP", "smtp"),
    ("Create administrator", "admin"), ("Ports and firewall", "firewall"),
    ("Configure game database host", "configure-database"),
    ("Show database host credentials", "database-credentials"),
    ("Back up local game databases", "backup-game-database"),
]


def menu(installer):
    from .core import InstallerError, Cancelled
    from .navigation import inventory, menu_items
    ui = installer.ui
    while True:
        state = inventory(installer)
        items = menu_items(ENTRIES, state)
        if ui.screen:
            ui.screen.wizard = None
            ui.screen.dashboard = state
            try:
                action = ui.screen.select("Overview", items, grouped=True)
            except Cancelled:
                return
        else:
            print()
            ui.banner()
            ui.card("Installation status", [ui.tr("Panel: {value}").format(value=ui.tr("Not installed" if state["panel"] == "absent" else state["panel"])),
                    ui.tr("Wings: {value}").format(value=ui.tr("Not installed" if state["wings"] == "absent" else state["wings"])),
                    "New machine? Start with Install Panel and Wings." if state["panel"] == "absent" else state.get("url", "")])
            last_group = None
            for item in items:
                if item.group != last_group:
                    print("\n  " + ui.paint(ui.tr(item.group), "35"))
                    last_group = item.group
                suffix = " · " + ui.tr("Unavailable") if not item.enabled else ""
                print(f"  {item.shortcut:>2}  {ui.tr(item.label)}{suffix}")
            print()
            selected = ui.ask("Choose an option", validator=lambda s: any(item.shortcut == s for item in items))
            item = next(item for item in items if item.shortcut == selected)
            if not item.enabled:
                ui.card("Before you continue", [item.reason])
                continue
            action = item.value
        if action == "exit":
            return
        if action == "refresh":
            continue
        if action == "language":
            try:
                select_language(ui)
            except Cancelled:
                pass
            except (InstallerError, OSError, ValueError) as exc:
                ui.say(installer.run.redact(str(exc)), "error")
                if ui.screen:
                    ui.screen.result("Language could not be changed")
            continue
        if ui.screen:
            ui.screen.begin()
        outcome = "Operation complete"
        try:
            installer.actions()[action]()
        except Cancelled:
            outcome = "Operation cancelled."
            ui.say(outcome, "muted")
        except (InstallerError, OSError, ValueError, KeyError) as exc:
            outcome = "Operation needs attention"
            ui.say(installer.run.redact(str(exc)), "error")
            ui.say("The operation did not complete. Review the private installer log.", "warn")
        if ui.screen:
            ui.screen.result(outcome)


def main(argv=None):
    from .core import Installer, InstallerError
    parser = argparse.ArgumentParser(description="Ptero Installer — multilingual Panel v2 and Wings setup for Ubuntu / Debian.")
    parser.add_argument("--language", choices=LANGUAGES, help="Skip the startup language selector")
    parser.add_argument("--no-animation", action="store_true", help="Disable terminal animations")
    parser.add_argument("--plain", action="store_true", help="Use numbered prompts instead of the full-screen TUI")
    parser.add_argument("--preview", action="store_true", help="Preview the interface without root or system changes")
    parser.add_argument("--version", action="version", version="ptero-installer " + __version__)
    parser.add_argument("action", nargs="?", help="Direct action, e.g. install-all, install-panel, diagnose, backup-panel")
    args = parser.parse_args(argv)
    ui = UI(animate=not args.no_animation, language=args.language or "en", plain=args.plain)
    installer = Installer(ui=ui)
    if args.action and args.action not in installer.actions():
        parser.error("Unknown action. Choices: " + ", ".join(installer.actions()))
    try:
        with ui.session():
            if args.language is None:
                select_language(ui)
            if args.preview:
                from .preview import show
                show(ui)
                return 0
            if os.geteuid() != 0:
                raise InstallerError("Run with sudo or as root.")
            os.umask(0o077)
            installer.p.base.mkdir(parents=True, exist_ok=True, mode=0o700)
            with (installer.p.base / ".lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise InstallerError("Another installer is already running.") from exc
                if args.action:
                    from .navigation import inventory, prerequisite
                    reason = prerequisite(args.action, inventory(installer))
                    if reason:
                        raise InstallerError(reason)
                    ui.banner()
                    installer.actions()[args.action]()
                    if ui.screen:
                        ui.screen.result()
                else:
                    menu(installer)
    except (KeyboardInterrupt, EOFError):
        ui.say("\nInterrupted. Keep the log and resume from the menu.", "warn")
        return 130
    except (InstallerError, OSError, ValueError, KeyError) as exc:
        ui.say(installer.run.redact(str(exc)), "error")
        return 1
    return 0
