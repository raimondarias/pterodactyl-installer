"""Read-only dashboard inventory and prerequisites shared by both interfaces."""
from dataclasses import dataclass


@dataclass
class Item:
    value: object
    label: str
    note: str = ""
    enabled: bool = True
    reason: str = ""
    shortcut: str = ""
    group: str = ""


GROUPS = ("Install", "Maintenance", "Game databases", "Backups", "Remove", "Preferences")
NOTES = {
    "install-all": "Set up the Panel and a Wings node with a guided review.",
    "install-panel": "Standalone is recommended. Choose your database, address and administrator.",
    "install-wings": "Install the game server daemon, then link it to your Panel.",
    "diagnose": "Check this machine and inspect managed services without changing them.",
    "configure-database": "Register a separate SQL host for game databases in the Panel.",
    "database-credentials": "View the saved private connection details for the provisioning account.",
    "backup-game-database": "Pause local game SQL briefly and create a consistent backup.",
    "update-panel": "Back up the Panel before updating its code and database schema.",
    "update-wings": "Update Wings with recovery of its previous binary or image on failure.",
    "restore-panel": "Restore a verified backup into an empty managed destination.",
    "uninstall-all": "Remove managed components. Game files and game SQL remain.",
    "uninstall-panel": "Back up first, then choose whether to retain Panel data.",
    "uninstall-wings": "Remove Wings while preserving game containers and files.",
    "configure-wings": "Use a node ID and Auto-Deploy token to link Wings.",
    "tls-wings": "Issue or renew the HTTPS certificate for the node address.",
    "backup-panel": "Save Panel SQL, original application keys and persistent configuration.",
    "backup-wings": "Save the node configuration before changing or removing Wings.",
    "restart": "Restart the managed services after a confirmation.",
    "logs": "Read recent service logs with secrets redacted.",
    "smtp": "Configure the Panel's outgoing email delivery.",
    "admin": "Create an additional administrator with a hidden password.",
    "firewall": "Review required ports without changing firewall rules.",
}


def inventory(installer):
    from .core import InstallerError
    result = {"panel": "absent", "wings": "absent", "database": "absent",
              "credentials": (installer.p.base / "game-database-credentials.json").is_file()}
    for key, path in (("panel", installer.p.state), ("wings", installer.p.wings_state),
                      ("database", installer.p.base / "game-databases/state.json")):
        if path.exists():
            try:
                state = installer.panel_state() if key == "panel" else installer.load(path)
                result[key] = state.get("status", "unknown")
                if key == "panel":
                    result["url"] = state.get("url", "")
                    result["method"] = state.get("method", "docker")
                    result["credentials"] |= bool(state.get("game_database", {}).get("registered"))
            except (OSError, ValueError, KeyError, InstallerError):
                result[key] = "invalid"
    return result


def prerequisite(action, state):
    panel, wings = state["panel"], state["wings"]
    if action in ("configure-database", "smtp", "admin", "update-panel", "backup-panel", "uninstall-panel"):
        if panel == "absent":
            return "Install the Panel first. Start with Install Panel or Install Panel and Wings."
        if panel == "invalid":
            return "The Panel state needs attention. Use diagnostics before changing it."
        if action in ("configure-database", "smtp", "admin", "update-panel") and panel != "ready":
            return "Finish or resume the Panel installation before using this option."
    if action in ("configure-wings", "tls-wings", "update-wings", "backup-wings", "uninstall-wings"):
        if wings == "absent":
            return "Install Wings first, then create or link a node in your Panel."
        if wings == "invalid":
            return "The Wings state needs attention. Use diagnostics before changing it."
    if action in ("restart", "logs", "uninstall-all") and panel == wings == "absent":
        return "There are no managed components yet. Start from Install."
    if action == "database-credentials" and not state["credentials"]:
        return "Configure a game database host first to save its connection details."
    if action == "backup-game-database" and state["database"] == "absent":
        return "No local game SQL host is configured. Remote SQL must be backed up on its own host."
    return ""


def group_for(action):
    if action.startswith("install-"):
        return "Install"
    if action.startswith("uninstall-"):
        return "Remove"
    if action in ("configure-database", "database-credentials", "backup-game-database"):
        return "Game databases"
    if action.startswith("backup-") or action == "restore-panel":
        return "Backups"
    return "Maintenance"


def menu_items(entries, state):
    result = []
    for number, (label, action) in enumerate(entries, 1):
        reason = prerequisite(action, state)
        result.append(Item(action, label, NOTES.get(action, ""), not reason, reason,
                           str(number), group_for(action)))
    result += [Item("language", "Change language", "Choose English, Spanish or Brazilian Portuguese.", shortcut="23", group="Preferences"),
               Item("exit", "Exit", "Return to your shell.", shortcut="0", group="Preferences")]
    return result
