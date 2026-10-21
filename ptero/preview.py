"""Side-effect-free terminal preview for reviewing the interface."""


def show(ui):
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
