"""Side-effect-free terminal preview for reviewing the interface."""


def show(ui):
    if ui.screen:
        return interactive(ui)
    ui.banner()
    ui.card("Interface preview", ["Preview only. No packages, files or services will be installed."])
    ui.step(1, 4, "Choose your installation")
    ui.card("Setup experience", ["1. " + ui.tr("Simple (Recommended)"), "2. " + ui.tr("Advanced")])
    ui.card("Panel deployment", ["1. " + ui.tr("Standalone (Recommended)"), "2. " + ui.tr("Docker")])
    ui.step(2, 4, "Address and connection")
    ui.card("How will you access the Panel?", ["1. " + ui.tr("Domain / subdomain (Recommended)"),
            "2. " + ui.tr("Public machine IP")])
    ui.step(3, 4, "Administrator and email")
    ui.card("First administrator", ["admin@example.com", "Your password is hidden and is never stored in the installer's state."])
    ui.step(4, 4, "Review your installation")
    ui.card("Game database host", ["MariaDB / MySQL: " + ui.tr("One engine selection for Panel and games."),
            ui.tr("Local node (isolated Docker database)"), ui.tr("Existing database host"), ui.tr("Configure later")])
    ui.card("Ready to install", [ui.tr("Deployment: {value}").format(value="Standalone"),
            ui.tr("Database: {value}").format(value="MariaDB"),
            ui.tr("Panel URL: {value}").format(value="https://panel.example.com")])
    with ui.busy("Checking your installation plan"):
        if ui.animate:
            import time
            time.sleep(0.4)


def interactive(ui):
    """Exercise real TUI widgets without calling installation backends."""
    from .core import Cancelled
    from .navigation import Item
    from .cli import select_language
    ui.screen.dashboard = {"panel": "absent", "wings": "absent", "database": "absent"}
    while True:
        ui.screen.wizard = None
        try:
            choice = ui.screen.select("Interface preview", [
                Item("wizard", "Explore the setup wizard", "Preview only. No packages, files or services will be installed.", shortcut="1"),
                Item("language", "Change language", shortcut="2"),
                Item("exit", "Exit preview", shortcut="0")])
            if choice == "exit":
                return
            if choice == "language":
                select_language(ui)
                continue
            ui.screen.begin()
            ui.step(1, 4, "Choose your installation")
            method = ui.choice("Panel deployment", [("standalone", "Standalone (Recommended)", "Native PHP, NGINX, database and Redis services"),
                                                     ("docker", "Docker", "Isolated Panel, database and Redis")])
            ui.step(2, 4, "Address and connection")
            address = ui.ask("Domain / subdomain (without http://)", "panel.example.com")
            ui.step(3, 4, "Administrator and email")
            ui.ask("Administrator email", "admin@example.com")
            ui.ask("Preview password (not saved)", secret=True)
            ui.step(4, 4, "Review your installation")
            with ui.busy("Checking your installation plan"):
                import time
                time.sleep(0.6)
            ui.card("Ready to install", [ui.tr("Deployment: {value}").format(value=method.title()),
                    ui.tr("Panel URL: {value}").format(value="https://" + address),
                    "Preview only. No packages, files or services will be installed."])
        except Cancelled:
            if ui.screen.wizard is None:
                return
