"""Collect node connection details without network or filesystem operations."""
from .core import Cancelled, valid_url


def connection(installer, known_url=None):
    ui = installer.ui
    ui.say("En el Panel: Admin → Locations → crea ubicación; Nodes → crea nodo → Configuration.")
    ui.say("Configura dominio, puertos API/SFTP, memoria, disco y allocations con la IP del nodo.")
    ui.say("El token solicitado es el de Auto-Deploy; se introducirá oculto.")
    url = ui.ask("URL del Panel", validator=valid_url).rstrip("/")
    if url.startswith("http:") and url != known_url:
        if not ui.yes("The Panel uses HTTP. Continue linking this node without HTTPS?"):
            raise Cancelled("Node linking cancelled.")
    node = ui.ask("ID numérico del nodo", validator=lambda s: s.isdigit() and int(s) > 0)
    token = ui.ask("Token Auto-Deploy", secret=True,
                   validator=lambda s: bool(s) and not any(c.isspace() for c in s))
    installer.run.secrets.add(token)
    ui.confirm("CONFIGURAR WINGS")
    return url, node, token
