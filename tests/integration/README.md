# Disposable machine integration

`deploy.py` performs a REAL root deployment. Run it only in a fresh, disposable Ubuntu/Debian VM with systemd and Docker-capable virtualization. It refuses recognizable existing websites. The `--disposable` flag explicitly selects this destructive test environment.

```bash
sudo python3 tests/integration/deploy.py --disposable --method standalone --engine mariadb
```

The script installs the actual Panel, runs service/HTTP diagnostics and makes a verified Panel backup. Private administrator credentials are saved only to `/root/ptero-integration-secrets.json` inside the VM. They must never be uploaded as artifacts.

The manual GitHub Actions workflow boots Ubuntu 22.04/24.04/26.04 and Debian 12/13 cloud VMs across both deployment methods and engines. `--cycle` also exercises service restart, update redeployment, purge and restoration with original application keys. Routine CI runs the isolated regression suite. Public TLS requires a domain routed to the VM, or `--url https://example.com --external-tls` with a preconfigured external HTTPS proxy. This option describes test infrastructure; it does not enable certificate issuance in the guest.
