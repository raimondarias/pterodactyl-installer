"""Verified local restores, consistent game archives and scheduled encrypted off-site copies."""
import contextlib
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import sys
import tarfile
import tempfile
from .core import InstallerError, atomic_write, write_json, secure_extract


def checksum(path):
    with Path(path).open('rb') as stream:
        return hashlib.sha256(stream.read()).hexdigest() if Path(path).stat().st_size < 1024 * 1024 else digest(stream)


def digest(stream):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(chunk)
    return h.hexdigest()


def verified(path):
    path = Path(path)
    sidecar = Path(str(path) + '.sha256')
    if not path.is_file() or not sidecar.is_file():
        raise InstallerError('A backup archive and its SHA-256 sidecar are required.')
    expected = sidecar.read_text().split()[0] if sidecar.read_text().split() else ''
    if not re.fullmatch('[0-9a-f]{64}', expected) or checksum(path) != expected:
        raise InstallerError('Backup checksum does not match; nothing was restored.')
    return path


def finish(partial, target):
    partial.chmod(0o600)
    partial.replace(target)
    atomic_write(Path(str(target) + '.sha256'), checksum(target) + '  ' + target.name + '\n')
    return target


def physical_archive(i, name, base, data, unit, extra=None):
    i.p.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = i.p.backups / (name + '-' + i.stamp() + '.tar.gz')
    partial = Path(str(target) + '.partial')
    was_running = i.run.run(['systemctl', 'is-active', '--quiet', unit], check=False)[0] == 0
    try:
        i.run.run(['systemctl', 'stop', unit], label='Pausing game SQL for a consistent backup')
        with tempfile.TemporaryDirectory(dir=i.p.backups) as temporary:
            manifest = Path(temporary) / 'manifest.json'
            write_json(manifest, {'schema': 1, 'owner': 'ptero-installer', 'type': 'game-sql-backup', **(extra or {})})
            with tarfile.open(partial, 'w:gz') as tar:
                tar.add(manifest, arcname='manifest.json')
                tar.add(base / 'state.json', arcname='state.json')
                tar.add(data, arcname='data')
        return finish(partial, target)
    finally:
        partial.unlink(missing_ok=True)
        if was_running:
            i.run.run(['systemctl', 'start', unit])


def restore_sql(i, archive=None):
    from .game_database import GameDatabase
    manager = GameDatabase(i)
    archive = verified(archive or i.ui.ask('Absolute backup archive path', validator=lambda v: Path(v).is_absolute()))
    if manager.state_file.exists() or (manager.data.exists() and any(manager.data.iterdir())):
        raise InstallerError('Game SQL restore requires an empty managed destination. Preserve or move existing SQL first.')
    i.p.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=i.p.backups) as temporary:
        work = Path(temporary)
        secure_extract(archive, work)
        state = i.load(work / 'state.json')
        if state.get('engine') not in ('mariadb', 'mysql') or not (work / 'data').is_dir() or not any((work / 'data').iterdir()):
            raise InstallerError('This is not a valid game SQL backup.')
        try:
            address = ipaddress.IPv4Address(state['host'])
            if (not address.is_private or address.is_loopback or address.is_unspecified
                    or type(state['port']) is not int or not 1 <= state['port'] <= 65535
                    or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,31}', state['username'])
                    or not all(isinstance(state[k], str) and 1 <= len(state[k]) <= 128 for k in ('password', 'root_password'))):
                raise ValueError
            for source in state.get('allowed_sources', []):
                source = ipaddress.IPv4Address(source)
                if not source.is_private or source.is_loopback or source.is_unspecified:
                    raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise InstallerError('This is not a valid game SQL backup.') from exc
        i.run.secrets.update((state['password'], state['root_password']))
        i.ui.confirm('RESTORE GAME DATABASES')
        if state.get('method') == 'standalone':
            from .native_game_database import NativeGameDatabase
            backend = NativeGameDatabase(manager)
            if backend.data.exists() and any(backend.data.iterdir()):
                raise InstallerError('Native game SQL restore requires an empty data directory.')
            backend.dependencies(state)
            _, version = i.run.run(['mysqld' if state['engine'] == 'mysql' else 'mariadbd', '--version'])
            if state.get('server_version') != version.strip():
                raise InstallerError('Physical SQL restore requires the original database server version.')
            if not state.get('allowed_sources'):
                i.docker()
                if manager.network(create=True, config=state.get('network_config')) != state['host']:
                    raise InstallerError('Restore the original private SQL network before importing its data.')
            backend.data.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            shutil.copytree(work / 'data', backend.data, dirs_exist_ok=True, symlinks=True)
            manager.base.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_json(manager.state_file, {**state, 'status': 'restoring'})
            backend.runtime(state)
            backend.client(state, 'SELECT 1;')
        else:
            if not re.fullmatch(r'[a-z0-9./_-]+@sha256:[0-9a-f]{64}', state.get('image', '')):
                raise InstallerError('Physical SQL restore requires the original pinned database image.')
            if manager.service.exists():
                unit = manager.service.read_text()
                if ('Description=Ptero isolated game SQL host' not in unit
                        or str(manager.compose) not in unit):
                    raise InstallerError('Unmanaged game database files exist; nothing was overwritten.')
                # Starting Docker can activate enabled Wants units. Freeze this
                # instance before ensuring Docker or copying its physical files.
                i.run.run(['systemctl', 'disable', '--now', 'ptero-game-databases.service'])
                if manager.compose.exists():
                    manager.dc('down')
            i.docker()
            if manager.network(create=True, config=state.get('network_config')) != state['host']:
                raise InstallerError('Restore the original private SQL network before importing its data.')
            i.run.run(['docker', 'pull', state['image']], label='Downloading the original game SQL image')
            manager.base.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copytree(work / 'data', manager.data, symlinks=True, dirs_exist_ok=True)
            write_json(manager.state_file, {**state, 'status': 'restoring'})
            atomic_write(manager.init, manager.init_sql(state))
            write_json(manager.compose, manager.config(state))
            manager.firewall(state)
            manager.service_config()
            manager.start(state)
        state['status'] = 'ready'
        write_json(manager.state_file, state)
    i.ui.say('Game databases restored with their original credentials.', 'ok')


def volumes(i):
    if not i.p.wings_state.exists():
        raise InstallerError('Install and configure Wings before backing up game files.')
    path = i.p.root / 'var/lib/pterodactyl/volumes'
    # Custom daemon_base must be handled explicitly rather than silently omitted.
    if i.p.config.is_file():
        text = i.p.config.read_text()
        if text.lstrip().startswith('{'):
            configured = json.loads(text).get('system', {}).get('data', '/var/lib/pterodactyl/volumes')
        else:
            block = re.search(r'(?m)^system:\s*\n((?:[ \t].*(?:\n|$))*)', text)
            match = re.search(r'(?m)^\s+data:\s*[\x27\"]?(/[^\n\x27\"]+)', block[1]) if block else None
            configured = match[1].strip() if match else '/var/lib/pterodactyl/volumes'
        if configured != '/var/lib/pterodactyl/volumes':
            raise InstallerError('Game-file backup currently requires the managed default Wings volume directory.')
    if path.is_symlink():
        raise InstallerError('The managed game volume directory cannot be a symlink.')
    return path


@contextlib.contextmanager
def paused_games(i, enabled):
    containers = []
    if enabled:
        _, output = i.run.run(['docker', 'ps', '-q', '--filter', 'label=Service=Pterodactyl', '--filter', 'status=running'])
        containers = output.split()
        if any(not re.fullmatch('[0-9a-f]{12,64}', item) for item in containers):
            raise InstallerError('Docker returned invalid game container identifiers.')
    try:
        if containers:
            i.run.run(['docker', 'pause', *containers], timeout=600, label='Pausing games for a consistent backup bundle')
        yield
    finally:
        if containers:
            i.run.run(['docker', 'unpause', *containers], timeout=600, label='Resuming game servers')


def backup_games(i):
    source = volumes(i)
    if not source.is_dir():
        raise InstallerError('No game volume directory exists to back up.')
    i.p.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = i.p.backups / ('game-files-' + i.stamp() + '.tar.gz')
    partial = Path(str(target) + '.partial')
    _, output = i.run.run(['docker', 'ps', '-q', '--filter', 'label=Service=Pterodactyl', '--filter', 'status=running'])
    containers = output.split()
    if any(not re.fullmatch('[0-9a-f]{12,64}', value) for value in containers):
        raise InstallerError('Docker returned invalid game container identifiers.')
    try:
        if containers:
            i.run.run(['docker', 'pause', *containers], label='Pausing game servers for file backup', timeout=600)
        with tarfile.open(partial, 'w:gz') as tar:
            tar.add(source, arcname='volumes')
        return finish(partial, target)
    finally:
        partial.unlink(missing_ok=True)
        if containers:
            i.run.run(['docker', 'unpause', *containers], label='Resuming game servers', timeout=600)


def restore_games(i, archive=None):
    target = volumes(i)
    archive = verified(archive or i.ui.ask('Absolute backup archive path', validator=lambda v: Path(v).is_absolute()))
    if target.exists() and any(target.iterdir()):
        raise InstallerError('Game-file restore requires an empty volume directory.')
    _, running = i.run.run(['docker', 'ps', '-q', '--filter', 'label=Service=Pterodactyl'])
    if running.strip():
        raise InstallerError('Stop all game servers before restoring their files.')
    i.ui.confirm('RESTORE GAME FILES')
    i.p.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=i.p.backups) as temporary:
        secure_extract(archive, temporary)
        source = Path(temporary) / 'volumes'
        if not source.is_dir():
            raise InstallerError('The backup contains no game volumes.')
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        if target.exists():
            target.rmdir()
        source.replace(target)


def backup_plan(ui):
    repository = ui.ask('Restic repository (local path, sftp: or s3:)', validator=lambda v: 1 <= len(v) <= 1024 and not any(ord(c) < 32 for c in v) and (v.startswith(('/', 's3:https://', 'sftp:'))))
    password = ui.ask('Backup encryption password (16+ characters)', secret=True, validator=lambda v: len(v) >= 16 and '\n' not in v)
    ui.ask('Confirm backup encryption password', secret=True, validator=lambda v: v == password)
    profile = {'schema': 1, 'owner': 'ptero-installer', 'repository': repository, 'environment': {}, 'keep_daily': 7,
               'keep_weekly': 4, 'games': ui.yes('Include game files? Running game servers pause during backup.', False),
               'backup_id': 'ptero-' + secrets.token_hex(8), 'calendar': ui.choice('Backup schedule', [('daily', 'Daily', ''), ('weekly', 'Weekly', ''), ('hourly', 'Hourly', '')])}
    if repository.startswith('s3:'):
        profile['environment']['AWS_ACCESS_KEY_ID'] = ui.ask('S3 access key', secret=True)
        profile['environment']['AWS_SECRET_ACCESS_KEY'] = ui.ask('S3 secret key', secret=True)
    if repository.startswith('sftp:'):
        ui.say('Prepare SSH keys and a verified known_hosts entry for the backup destination first.')
    return profile, password


class ScheduledBackups:
    def __init__(self, i):
        self.i, self.p, self.ui, self.run = i, i.p, i.ui, i.run
        self.profile = self.p.base / 'backup-profile.json'

    def environment(self, profile):
        env = {'RESTIC_REPOSITORY': profile['repository'], 'RESTIC_PASSWORD_FILE': str(self.p.base / 'backup-password')}
        env.update(profile.get('environment', {}))
        self.run.secrets.update(env.values())
        password = self.p.base / 'backup-password'
        if password.is_file():
            self.run.secrets.add(password.read_text().strip())
        return env

    def configure(self):
        profile, password = backup_plan(self.ui)
        self.ui.confirm('CONFIGURE BACKUPS')
        if self.profile.exists():
            profile['backup_id'] = self.i.load(self.profile)['backup_id']
        if not shutil.which('restic'):
            self.run.run(['apt-get', 'update'])
            self.run.run(['apt-get', 'install', '-y', 'restic'])
        self.run.secrets.add(password)
        env = self.environment(profile)
        candidate = self.p.base / ('backup-password-' + secrets.token_hex(8))
        try:
            atomic_write(candidate, password + '\n')
            env['RESTIC_PASSWORD_FILE'] = str(candidate)
            if self.run.run(['restic', 'snapshots', '--json'], env=env, check=False)[0]:
                self.run.run(['restic', 'init'], env=env, label='Initializing encrypted backup repository')
            candidate.replace(self.p.base / 'backup-password')
        finally:
            candidate.unlink(missing_ok=True)
        write_json(self.profile, profile)
        # Stable private runtime: scheduled jobs must not depend on bootstrap temp files.
        runtime = self.p.base / 'runtime'
        runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        source = Path(__file__).resolve().parent
        shutil.copytree(source, runtime / 'ptero', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
        atomic_write(runtime / 'installer.py', 'from ptero.cli import main\nraise SystemExit(main())\n')
        command = shlex.join([str(self.p.root / 'usr/bin/python3'), str(runtime / 'installer.py'), '--language', self.ui.language, 'backup-run'])
        atomic_write(self.p.root / 'etc/systemd/system/ptero-backup.service', '[Unit]\nDescription=Ptero encrypted backups\nAfter=network-online.target\n[Service]\nType=oneshot\nUMask=0077\nNice=10\nIOSchedulingClass=idle\n' + f'ExecStart={command}\n', 0o644)
        atomic_write(self.p.root / 'etc/systemd/system/ptero-backup.timer', '[Unit]\nDescription=Ptero scheduled backups\n[Timer]\n' + f"OnCalendar={profile['calendar']}\nPersistent=true\nRandomizedDelaySec=300\n[Install]\nWantedBy=timers.target\n", 0o644)
        self.run.run(['systemctl', 'daemon-reload'])
        self.run.run(['systemctl', 'enable', '--now', 'ptero-backup.timer'])

    def run_now(self):
        profile = self.i.load(self.profile)
        env = self.environment(profile)
        self.p.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix='bundle-', dir=self.p.backups) as temporary:
            bundle = Path(temporary)
            with paused_games(self.i, profile.get('games', False)):
                artifacts = []
                if self.p.state.exists():
                    artifacts.append(self.i.backup_panel())
                from .game_database import GameDatabase
                sql = GameDatabase(self.i)
                if sql.state_file.exists():
                    artifacts.append(sql.backup())
                if self.p.wings_state.exists():
                    self.i.backup_wings()
                    shutil.copy2(self.p.wings_state, bundle / 'wings-state.json')
                    if self.p.config.exists():
                        shutil.copy2(self.p.config, bundle / 'wings-config.yml')
                if profile.get('games'):
                    artifacts.append(backup_games(self.i))
            if not artifacts and not any(bundle.iterdir()):
                raise InstallerError('There are no managed resources to back up.')
            for archive in artifacts:
                verified(archive)
                shutil.copy2(archive, bundle / archive.name)
                shutil.copy2(str(archive) + '.sha256', bundle / (archive.name + '.sha256'))
            self.run.run(['restic', 'backup', '--tag', 'ptero-installer', '--host', profile['backup_id'], '.'], env=env,
                         label='Uploading encrypted backup bundle', timeout=14400, cwd=str(bundle))
        # Retention only touches this installer's tagged snapshots.
        self.run.run(['restic', 'forget', '--tag', 'ptero-installer', '--host', profile['backup_id'], '--keep-daily', str(profile['keep_daily']), '--keep-weekly', str(profile['keep_weekly']), '--prune'], env=env, timeout=14400)
        self.run.run(['restic', 'check'], env=env, label='Checking encrypted backup repository', timeout=14400)

        history_path = self.p.base / 'backup-history.json'
        history = self.i.load(history_path) if history_path.exists() else {'schema': 1, 'owner': 'ptero-installer', 'runs': []}
        history['runs'].append([str(path) for path in artifacts])
        while len(history['runs']) > profile.get('keep_local', 3):
            for value in history['runs'].pop(0):
                path = Path(value)
                if path.parent.resolve() == self.p.backups.resolve() and not path.is_symlink():
                    path.unlink(missing_ok=True)
                    Path(str(path) + '.sha256').unlink(missing_ok=True)
        write_json(history_path, history)

    def download(self):
        profile = self.i.load(self.profile)
        env = self.environment(profile)
        _, output = self.run.run(['restic', 'snapshots', '--json', '--tag', 'ptero-installer', '--host', profile['backup_id']], env=env)
        snapshots = json.loads(output)
        if not snapshots:
            raise InstallerError('No managed snapshots exist in this repository.')
        self.ui.card('Available backup snapshots', [str(item['id']) + ' ' + str(item.get('time', '')) for item in snapshots])
        snapshot = self.ui.ask('Snapshot ID', snapshots[-1]['id'], lambda v: any(s['id'] == v for s in snapshots))
        self.ui.confirm('DOWNLOAD BACKUP')
        self.p.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = Path(tempfile.mkdtemp(prefix='download-', dir=self.p.backups))
        self.run.run(['restic', 'restore', snapshot, '--target', destination], env=env, timeout=14400)
        for archive in destination.rglob('*.tar.gz'):
            verified(archive)
        self.ui.say(self.ui.tr('Downloaded backup directory: {value}').format(value=destination), 'ok')
        return destination
