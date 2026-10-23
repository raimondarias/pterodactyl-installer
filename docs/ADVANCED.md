# Nodes, recovery and backups

These operations are available in the grouped TUI and by direct action. Preview mode simulates the workflows without contacting hosts or installing services.

## Automatic first node

Use **Nodes → Create node and allocations**, or choose automatic creation when linking Wings on the managed Panel machine. Supply a location code, node name/address, memory/disk limits, API/SFTP ports and allocation IPv4/range. The installer uses Panel v2's location, node and allocation creation contracts. Existing matching nodes are reused; conflicting settings stop the operation.

HTTPS Panels require HTTPS node addresses. An existing reverse proxy can terminate node TLS; otherwise the local or remote node needs its own working DNS and certificate. Creation alone does not open game allocation ports at the hosting provider. Local linking backs up the old configuration before writing the new one.

## Isolated native game SQL

Choose the database engine once in the Panel wizard. For local game SQL, select an isolated native instance or Docker. Native SQL has a separate datadir, socket, port, systemd service and provisioning account; it never grants the game provisioning user access to the Panel SQL instance.

The local native instance binds to the private game bridge. Docker remains required for game containers and this bridge, even though SQL itself runs natively. Its service starts after Docker, and its own input rules restrict SQL to local bridges. Game SQL and its credentials remain independent when the Panel is removed.

## Restore game databases and files

- **Restore game databases** verifies the archive checksum, ownership metadata, original engine/image or native server version, and private network settings. The destination must be empty. Physical restore starts the original image or matching native version, then checks readiness. Original provisioning and game-account credentials remain in the restored SQL data.
- **Back up game files** freezes only running containers with the Pterodactyl service label, copies the managed volume directory and unfreezes those containers even if archiving fails.
- **Restore game files** requires stopped games and an empty destination, verifies SHA-256 and safely extracts the archive while preserving file ownership. The initial implementation supports Wings' default `/var/lib/pterodactyl/volumes` directory; custom daemon paths are rejected explicitly.

Panel SQL, game SQL and game files are separate restore operations. Restore the original Panel keys and records alongside game SQL to retain encrypted database credentials.

## Encrypted scheduled backups

Use **Schedule encrypted backups**. Choose a local Restic repository, `sftp:user@host:path` or `s3:https://endpoint/bucket`, supply the encryption password, select daily/weekly/hourly and optionally include game files. S3 credentials and the encryption password are stored in private root-only files. SFTP requires preconfigured SSH keys and a verified host key.

The installer installs Restic if needed, validates or initializes the encrypted repository and installs `ptero-backup.timer`. A private runtime copy makes scheduled jobs independent of the online launcher's temporary directory. **Run scheduled backup now** performs the same job immediately.

When game files are included, games remain paused while the Panel, SQL and files are captured, then resume before uploading. Restic uploads a complete bundle, applies seven daily/four weekly retention within this installation's unique snapshot scope and checks repository integrity. Only successful runs trigger cleanup of older scheduler-created local archives; the latest three runs are retained. Manually created archives are not deleted.

**Download remote backup** lists this installation's snapshots, restores the selected one into a new private directory and verifies archive checksums. Apply the individual restore commands to empty destinations afterward. Keep the repository password outside the server: the installer cannot recover a lost encryption password.

## Resume and health

Installation phases persist `running`, `failed` and `done` states. A completed phase is skipped only when it supplies a successful validation for the same release. Migrations remain idempotent and run again when needed; error text containing credentials is never saved in phase state. Use **Resume installation** after correcting the reported problem.

**Detailed health report** collects disk/memory pressure, service/container failures, migrations, queue failures, Panel HTTP/TLS, Wings and backup timer results. One failing component does not hide the other findings. It reports issues without restarting services or changing firewall rules.

## Remote machines

**Install remote Wings node** and **Prepare remote game SQL** use root SSH, an existing private key and an explicitly selected verified `known_hosts` file. Host-key checking is strict. Python 3 must already be present remotely. Runtime source travels over SSH with a SHA-256 check; credentials travel through encrypted stdin instead of command arguments.

Remote Wings creates the Panel node and allocations, then installs and configures the daemon. A failed remote operation leaves the Panel node available for diagnosis/retry. Remote SQL requires an assigned private IPv4 and explicit private source addresses. Its separate native instance and firewall restrict provisioning access to those sources; the Panel then validates and registers the host. VPN/private routing and the provider firewall must already connect the machines. No private keys are copied into the runtime package.
