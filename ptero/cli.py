"""Language selection, grouped maintenance menu and process locking."""
import argparse
import fcntl
import os
import sys

from . import __version__
from .i18n import LANGUAGES
from .ui import UI


def select_language(ui):
    print("\n  LANGUAGE\n")
    language = ui.choice("Which language would you like to use?", [
        ("en", "English", ""), ("es", "Español", ""), ("pt-BR", "Português (Brasil)", "")])
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
    from .core import InstallerError
    ui = installer.ui
    while True:
        print()
        ui.banner()
        if installer.p.state.exists():
            state = installer.panel_state()
            ui.say(f"{state.get('method', 'docker').title()} · {state.get('database_engine', 'mariadb').upper()} · {state['version']} · {ui.tr(state['status'])}", "muted")
            ui.say(state["url"], "muted")
        groups = {1: "INSTALL & REMOVE", 7: "UPDATE & CONNECT", 11: "BACKUP & RESTORE", 14: "OPERATIONS", 20: "GAME DATABASES"}
        for number, (label, _) in enumerate(ENTRIES, 1):
            if number in groups:
                print("\n  " + ui.paint(ui.tr(groups[number]), "35"))
            print(f"  {number:2}  {ui.tr(label)}")
        language_option = len(ENTRIES) + 1
        print(f"\n  {language_option}  " + ui.tr("Change language"))
        print("   0  " + ui.tr("Exit") + "\n")
        selected = int(ui.ask("Choose an option", validator=lambda s: s.isdigit() and 0 <= int(s) <= language_option))
        if selected == 0:
            return
        if selected == language_option:
            try:
                select_language(ui)
            except (InstallerError, OSError, ValueError) as exc:
                ui.say(installer.run.redact(str(exc)), "error")
            continue
        try:
            installer.actions()[ENTRIES[selected - 1][1]]()
        except (InstallerError, OSError, ValueError, KeyError) as exc:
            ui.say(installer.run.redact(str(exc)), "error")
            ui.say("The operation did not complete. Review the private installer log.", "warn")


def main(argv=None):
    from .core import Installer, InstallerError
    parser = argparse.ArgumentParser(description="Ptero Installer — multilingual Panel v2 and Wings setup for Ubuntu / Debian.")
    parser.add_argument("--language", choices=LANGUAGES, help="Skip the startup language selector")
    parser.add_argument("--no-animation", action="store_true", help="Disable terminal animations")
    parser.add_argument("--preview", action="store_true", help="Preview the interface without root or system changes")
    parser.add_argument("--version", action="version", version="ptero-installer " + __version__)
    parser.add_argument("action", nargs="?", help="Direct action, e.g. install-all, install-panel, diagnose, backup-panel")
    args = parser.parse_args(argv)
    ui = UI(animate=not args.no_animation, language=args.language or "en")
    installer = Installer(ui=ui)
    if args.action and args.action not in installer.actions():
        parser.error("Unknown action. Choices: " + ", ".join(installer.actions()))
    try:
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
                ui.banner()
                installer.actions()[args.action]()
            else:
                menu(installer)
    except (KeyboardInterrupt, EOFError):
        ui.say("\nInterrupted. Keep the log and resume from the menu.", "warn")
        return 130
    except (InstallerError, OSError, ValueError, KeyError) as exc:
        ui.say(installer.run.redact(str(exc)), "error")
        return 1
    return 0
