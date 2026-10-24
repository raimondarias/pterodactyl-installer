# Disposable machine integration

`deploy.py` performs a REAL root deployment. Run it only in a fresh, disposable Ubuntu/Debian VM with systemd and Docker-capable virtualization. It refuses recognizable existing websites. The `--disposable` flag explicitly selects this destructive test environment.

```bash
sudo python3 tests/integration/deploy.py --disposable --method standalone --engine mariadb
```

The script installs the actual Panel, runs service/HTTP diagnostics and makes a verified Panel backup. Private administrator credentials are saved only to `/root/ptero-integration-secrets.json` inside the VM. They must never be uploaded as artifacts.

The manual GitHub Actions workflow boots Ubuntu 22.04/24.04/26.04 and Debian 12/13 cloud VMs across both deployment methods and engines. `--cycle` also exercises service restart, update redeployment, purge and restoration with original application keys. `--full` adds automatic node linking, game SQL host provisioning and a real Minetest server. Current installer backups cover only Panel and Wings configuration. Historical 1.2.0 integration results include game-data backup/restore checks that have since been removed; retain those records as historical evidence rather than current feature documentation. Docker Panel cases use Docker game SQL; standalone cases use native game SQL. Routine CI runs the isolated regression suite. Public TLS requires a domain routed to the VM, or `--url https://example.com --external-tls` with a preconfigured external HTTPS proxy. This option describes test infrastructure; it does not enable certificate issuance in the guest.

Ubuntu 26.04 is covered by Docker integration. Fresh standalone setup needs a separately configured PHP 8.3/8.4 package source: the tested Ondřej PPA currently has no resolute Release index. The installer stops before package changes when that prerequisite is missing. The automated fresh-VM matrix excludes those two unavailable native cases.
