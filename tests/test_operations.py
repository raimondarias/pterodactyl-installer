"""New node, recovery, backup, native SQL and SSH boundary regressions."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from unittest.mock import patch
from test_installer import BaseTest, QuietUI
from ptero.core import InstallerError, write_json
from ptero.phases import Phases
from ptero.nodes import CREATE, create, port_range
from ptero.game_database import GameDatabase
from ptero.native_game_database import NativeGameDatabase
from ptero.remote import AGENT, execute, private_ipv4, ssh
from ptero.backups import ScheduledBackups, checksum, verified, restore_sql, backup_games, restore_games


class OperationsTests(BaseTest):
    def test_native_game_sql_refuses_mysql_community_before_package_changes(self):
        backend = NativeGameDatabase(GameDatabase(self.installer))
        calls = []
        def command(args, **kwargs):
            calls.append(args)
            return (0, 'install ok installed') if args[-1] == 'mysql-community-server' else (1, '')
        with patch.object(self.installer, 'check_host', return_value={'ID':'debian','VERSION_CODENAME':'trixie'}), patch.object(self.runner, 'run', side_effect=command):
            with self.assertRaisesRegex(InstallerError, 'different database engine'):
                backend.dependencies({'engine':'mariadb'})
        self.assertFalse(any(args[0]=='apt-get' for args in calls))

    def test_wings_subnet_avoids_panel_compose_and_host_routes(self):
        from ptero.networking import wings_network
        replies = ['panel\nhost\nnone\n', json.dumps([{'Name':'host','IPAM':{'Config':None}}, {'Name':'none','IPAM':None},
                   {'Name':'panel_default','IPAM':{'Config':[{'Subnet':'172.18.0.0/16'}]}}]),
                   json.dumps([{'dst':'default'},{'dst':'172.30.0.0/24'}])]
        with patch.object(self.runner, 'run', side_effect=[(0, value) for value in replies]):
            result = wings_network(self.installer, {})
        self.assertEqual(result['docker']['network']['interfaces']['v4']['subnet'], '172.30.1.0/24')

    def test_wings_reuses_existing_bridge_and_preserves_explicit_configuration(self):
        from ptero.networking import wings_network
        replies = ['wings', json.dumps([{'Name':'pterodactyl_nw','IPAM':{'Config':[{'Subnet':'10.20.0.0/24','Gateway':'10.20.0.1'}]}}]), '[]']
        with patch.object(self.runner, 'run', side_effect=[(0, value) for value in replies]):
            config = wings_network(self.installer, {})
        self.assertEqual(config['docker']['network']['interface'], '10.20.0.1')
        with patch.object(self.runner, 'run') as run:
            self.assertIs(wings_network(self.installer, config), config)
        run.assert_not_called()

    def test_apparmor_game_sql_rules_preserve_existing_local_rules(self):
        backend = NativeGameDatabase(GameDatabase(self.installer))
        directory = self.paths.root/'etc/apparmor.d'
        (directory/'local').mkdir(parents=True)
        (directory/'usr.sbin.mysqld').write_text('#include <local/usr.sbin.mysqld>\n')
        local = directory/'local/usr.sbin.mysqld'
        local.write_text('/custom/site/** r,\n')
        backend.apparmor(); backend.apparmor()
        text = local.read_text()
        self.assertIn('/custom/site/** r,', text)
        self.assertEqual(text.count('# BEGIN PTERO GAME SQL'), 1)
        self.assertIn(str(backend.data)+'/** rwk,', text)
        self.assertNotIn('/var/lib/mysql/**', text)

    def test_modern_mariadb_apparmor_profile_gets_scoped_local_rules(self):
        backend = NativeGameDatabase(GameDatabase(self.installer))
        directory = self.paths.root/'etc/apparmor.d'
        directory.mkdir(parents=True)
        (directory/'mariadbd').write_text('profile mariadbd /usr/sbin/mariadbd {\n include if exists <local/mariadbd>\n}\n')
        backend.apparmor()
        self.assertIn(str(backend.data)+'/** rwk,', (directory/'local/mariadbd').read_text())
        self.assertTrue(any(args[:2]==['apparmor_parser','-r'] for args,_ in self.runner.calls))

    def test_wings_has_one_start_to_avoid_concurrent_bridge_creation(self):
        self.wings()
        with patch('ptero.core.time.sleep'):
            self.installer.start_wings()
        commands=[args for args,_ in self.runner.calls if args[0]=='systemctl']
        self.assertIn(['systemctl','enable','wings'], commands)
        self.assertEqual(sum(args[1]=='restart' or '--now' in args for args in commands), 1)

    def test_failed_phase_persists_failure_without_exception_secrets_and_can_resume(self):
        state = {'version': 'v2'}
        saves = []
        phases = Phases(self.installer, state, lambda: saves.append(json.loads(json.dumps(state))))
        with self.assertRaises(ValueError):
            phases.run('migration', lambda: (_ for _ in ()).throw(ValueError('secret-password')))
        self.assertEqual(state['phases']['migration']['status'], 'failed')
        self.assertNotIn('secret-password', json.dumps(saves))
        phases.run('migration', lambda: None)
        self.assertEqual(state['phases']['migration']['status'], 'done')
        self.assertEqual(saves[0]['phases']['migration']['status'], 'running')

    def test_completed_phase_requires_live_validation_and_matching_version(self):
        state = {'version': 'v2'}
        phases = Phases(self.installer, state, lambda: None)
        calls = []
        phases.run('source', lambda: calls.append(1))
        phases.run('source', lambda: calls.append(2), lambda: True)
        phases.run('source', lambda: calls.append(3), lambda: False)
        state['version'] = 'v3'
        phases.run('source', lambda: calls.append(4), lambda: True)
        self.assertEqual(calls, [1, 3, 4])

    def test_node_port_ranges_reject_system_ports_reverse_and_excessive_ranges(self):
        for value in ('25565', '25565-25575', '1025-2024'):
            self.assertTrue(port_range(value))
        for value in ('22', '1024', '8080-8000', '1025-2025', '1; id', '65536'):
            self.assertFalse(port_range(value))

    def test_node_provisioning_uses_contracts_and_saves_tokens_privately(self):
        self.panel()
        from test_installer import node_payload
        payload = {'node_id': 3, 'configuration': node_payload()}
        with patch('ptero.nodes.execute', return_value=payload) as bridge:
            result = create(self.installer, {'name': 'Node 1'})
        self.assertEqual(result['node_id'], 3)
        self.assertIn('CreatesNodes', bridge.call_args.args[1])
        self.assertIn('CreatesAllocations', bridge.call_args.args[1])
        report = self.paths.base / 'node-provisioning.json'
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        self.assertIn('valid-node-token', self.runner.secrets)

    def test_node_php_has_valid_real_parser_syntax(self):
        if not shutil.which('php'):
            self.skipTest('PHP CLI unavailable')
        path = Path(self.temporary.name) / 'node.php'
        path.write_text('<?php\n' + CREATE)
        result = subprocess.run(['php', '-l', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ssh_provisioning_keeps_credentials_in_stdin_and_host_keys_enforced(self):
        target = {'host': 'node.example.com', 'port': 2222, 'identity': '/root/key', 'known_hosts': '/root/known_hosts'}
        original = self.runner.run
        captured = []
        def run(args, **kwargs):
            captured.append(kwargs['input_file'].read())
            return 0, 'PTERO_REMOTE_SUCCESS'
        self.runner.run = run
        execute(self.installer, target, {'action': 'database', 'settings': {'password': 'private-secret'}})
        self.assertIn(b'private-secret', captured[0])
        self.assertIn('StrictHostKeyChecking=yes', ssh(target))
        self.assertNotIn('private-secret', ' '.join(ssh(target)))
        compile(AGENT, 'agent', 'exec')
        self.runner.run = original

    def test_remote_database_requires_private_routed_ipv4(self):
        for value in ('10.2.3.4', '172.20.1.3', '192.168.3.4'):
            self.assertTrue(private_ipv4(value))
        for value in ('8.8.8.8', '127.0.0.1', '169.254.1.2', '0.0.0.0', '::1', 'invalid'):
            self.assertFalse(private_ipv4(value))

    def test_native_sql_uses_own_datadir_socket_and_service(self):
        manager = GameDatabase(self.installer)
        backend = NativeGameDatabase(manager)
        state = {'engine': 'mariadb', 'host': '172.25.0.1', 'port': 3307}
        with patch.object(backend, 'client', return_value=(0, '1')):
            backend.runtime(state)
        config = backend.config.read_text()
        self.assertIn('port=3307', config)
        self.assertIn('game-sql', config)
        self.assertEqual(backend.config.parent.stat().st_mode & 0o777, 0o755)
        self.assertEqual(backend.config.stat().st_mode & 0o777, 0o640)
        initialization = [(args, kwargs) for args, kwargs in self.runner.calls
                          if kwargs.get('label') == 'Initializing isolated native game SQL']
        self.assertEqual(initialization[0][0][:4], ['runuser', '-u', 'ptero-game-sql', '--'])
        self.assertEqual(initialization[0][1]['cwd'], str(backend.data))
        self.assertNotIn('ptero_panel', config)
        unit = self.paths.root / ('etc/systemd/system/' + backend.unit)
        self.assertIn('ExecStartPre=+', unit.read_text())
        self.assertIn('RuntimeDirectory=ptero-game-sql', unit.read_text())

    def test_native_firewall_remote_allowlist_has_no_public_wildcard_rule(self):
        backend = NativeGameDatabase(GameDatabase(self.installer))
        script = backend.firewall({'host': '10.1.2.3', 'port': 3307, 'allowed_sources': ['10.1.2.4']}).read_text()
        self.assertIn('-s 10.1.2.4', script)
        self.assertIn('-j DROP', script)
        self.assertNotIn('0.0.0.0/0', script)
        self.assertNotIn('-F ', script)

    def make_sql_archive(self):
        work = Path(self.temporary.name) / 'source'
        work.mkdir()
        state = {'schema': 1, 'owner': 'ptero-installer', 'engine': 'mariadb', 'host': '172.25.0.1', 'port': 3307,
                 'username': 'manager', 'password': 'original-game-password', 'root_password': 'original-root-password',
                 'image': 'mariadb@sha256:' + 'a' * 64}
        write_json(work / 'state.json', state)
        (work / 'data').mkdir(); (work / 'data/table.dat').write_text('SQL DATA')
        archive = Path(self.temporary.name) / 'sql.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for path in work.iterdir():
                tar.add(path, arcname=path.name)
        Path(str(archive) + '.sha256').write_text(checksum(archive) + '  sql.tar.gz\n')
        return archive

    def test_sql_restore_verifies_hash_preserves_credentials_and_waits_for_health(self):
        archive = self.make_sql_archive()
        with patch.object(self.installer, 'docker'), patch.object(GameDatabase, 'network', return_value='172.25.0.1'), \
             patch.object(GameDatabase, 'firewall'), patch.object(GameDatabase, 'service_config'):
            restore_sql(self.installer, archive)
        state = self.installer.load(GameDatabase(self.installer).state_file)
        self.assertEqual(state['password'], 'original-game-password')
        self.assertEqual(state['status'], 'ready')
        self.assertEqual((GameDatabase(self.installer).data / 'table.dat').read_text(), 'SQL DATA')
        self.assertTrue(any('--wait' in args for args, _ in self.runner.calls))

    def test_sql_restore_refuses_existing_data_and_bad_checksum(self):
        archive = self.make_sql_archive()
        Path(str(archive) + '.sha256').write_text('0' * 64)
        with self.assertRaisesRegex(InstallerError, 'checksum'):
            restore_sql(self.installer, archive)
        self.assertEqual(self.runner.calls, [])

    def test_game_file_roundtrip_preserves_content_and_rejects_nonempty_destination(self):
        self.wings()
        source = self.paths.root / 'var/lib/pterodactyl/volumes'
        source.mkdir(parents=True)
        (source / 'world.dat').write_text('WORLD')
        archive = backup_games(self.installer)
        self.assertTrue(verified(archive))
        with self.assertRaisesRegex(InstallerError, 'empty'):
            restore_games(self.installer, archive)
        shutil.rmtree(source)
        restore_games(self.installer, archive)
        self.assertEqual((source / 'world.dat').read_text(), 'WORLD')

    def test_health_report_collects_multiple_failures_instead_of_hiding_them(self):
        self.panel()
        from ptero.health import inspect
        with patch('ptero.health.urllib.request.urlopen', side_effect=OSError('offline')):
            rows = inspect(self.installer)
        self.assertTrue(any('Panel containers' in row for row in rows))
        self.assertTrue(any('Panel HTTP endpoint' in row for row in rows))

    def test_health_reports_pending_migrations_and_queue_failures_in_docker(self):
        self.panel()
        from ptero.health import inspect
        def command(*args, **kwargs):
            if 'migrate:status' in args:return 0, '2026_10_23_create_games ........ Pending\n'
            if 'queue:failed' in args:return 0, '17 failed jobs\n'
            return 0, '[]'
        with patch.object(self.installer, 'dc', side_effect=command), patch('ptero.health.urllib.request.urlopen', side_effect=OSError('offline')):
            rows=inspect(self.installer)
        self.assertTrue(any('Needs attention: Panel SQL and migrations' in row for row in rows))
        self.assertTrue(any('Needs attention: Queue failures' in row for row in rows))

    def test_menu_shortcuts_remain_unique_with_language_23_reserved(self):
        from ptero.cli import ENTRIES
        from ptero.navigation import inventory, menu_items
        items = menu_items(ENTRIES, inventory(self.installer))
        values = [item.shortcut for item in items]
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(next(i for i in items if i.shortcut == '23').value, 'language')

    def test_actual_encrypted_repository_roundtrip(self):
        binary = shutil.which('restic') or ('/root/ptero-lab/tools/usr/bin/restic' if Path('/root/ptero-lab/tools/usr/bin/restic').exists() else None)
        if not binary:
            self.skipTest('Restic executable unavailable')
        root = Path(self.temporary.name)
        archive = self.make_sql_archive()
        repository = root / 'encrypted-repo'
        self.paths.base.mkdir(parents=True, exist_ok=True)
        (self.paths.base / 'backup-password').write_text('test-encryption-password-123!\n')
        profile = {'schema': 1, 'owner': 'ptero-installer', 'repository': str(repository), 'backup_id': 'test-instance',
                   'environment': {}, 'keep_daily': 7, 'keep_weekly': 4, 'games': False}
        write_json(self.paths.base / 'backup-profile.json', profile)
        scheduler = ScheduledBackups(self.installer)
        env = scheduler.environment(profile)
        subprocess.run([binary, 'init'], env={**os.environ, **env}, capture_output=True, check=True)
        self.panel()
        original = self.runner.run
        def run(args, **kwargs):
            if str(args[0]) == 'restic':
                result = subprocess.run([binary, *map(str, args[1:])], cwd=kwargs.get('cwd'), env={**os.environ, **kwargs.get('env', {})}, capture_output=True, text=True)
                if result.returncode:
                    raise InstallerError(result.stderr)
                return result.returncode, result.stdout
            return original(args, **kwargs)
        self.runner.run = run
        with patch.object(self.installer, 'backup_panel', return_value=archive):
            scheduler.run_now()
        destination = scheduler.download()
        restored = list(destination.rglob('sql.tar.gz'))
        self.assertEqual(len(restored), 1)
        self.assertEqual(checksum(restored[0]), checksum(archive))
        self.assertNotIn(b'original-game-password', b''.join(p.read_bytes() for p in repository.rglob('*') if p.is_file()))

    def test_nested_game_backup_does_not_unpause_a_container_paused_by_the_bundle(self):
        from ptero.backups import paused_games
        self.wings()
        source = self.paths.root / 'var/lib/pterodactyl/volumes'
        source.mkdir(parents=True)
        (source / 'world').write_text('GAME')
        paused = False
        actions = []
        original = self.runner.run
        def run(args, **kwargs):
            nonlocal paused
            args = list(map(str, args))
            if args[:2] == ['docker', 'ps']:
                self.assertIn('status=running', args)
                return 0, '' if paused else 'a' * 12
            if args[:2] == ['docker', 'pause']:
                self.assertFalse(paused); paused = True; actions.append('pause'); return 0, ''
            if args[:2] == ['docker', 'unpause']:
                self.assertTrue(paused); paused = False; actions.append('unpause'); return 0, ''
            return original(args, **kwargs)
        self.runner.run = run
        with paused_games(self.installer, True):
            archive = backup_games(self.installer)
            self.assertTrue(paused)
        self.assertFalse(paused)
        self.assertEqual(actions, ['pause', 'unpause'])
        self.assertTrue(verified(archive))

    def test_sigterm_in_plain_scheduled_session_unpauses_games_before_exit(self):
        import signal
        from ptero.backups import paused_games
        actions = []
        def run(args, **kwargs):
            args = list(map(str, args))
            if args[:2] == ['docker', 'ps']:
                return 0, 'a' * 12
            actions.append(args[1]); return 0, ''
        self.runner.run = run
        previous = signal.getsignal(signal.SIGTERM)
        with self.assertRaises(KeyboardInterrupt):
            with self.ui.session():
                with paused_games(self.installer, True):
                    signal.raise_signal(signal.SIGTERM)
        self.assertEqual(actions, ['pause', 'unpause'])
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)

    def test_native_health_waits_for_php_socket_readiness_after_reload(self):
        from unittest.mock import MagicMock
        from ptero.native import NativeBackend
        backend = NativeBackend(self.installer, {**self.state, 'method': 'standalone'})
        responses = [MagicMock(), MagicMock()]
        responses[0].getresponse.return_value.status = 502
        responses[1].getresponse.return_value.status = 200
        with patch('ptero.native.http.client.HTTPConnection', side_effect=responses) as connect, patch('ptero.native.time.sleep') as sleep:
            backend.health()
        self.assertEqual(connect.call_count, 2)
        sleep.assert_called_once_with(1)
        for response in responses:
            response.close.assert_called_once()

    def test_mysql_authentication_plugin_is_saved_verified_and_repaired(self):
        state = {**self.state, 'method': 'docker', 'database_engine': 'mysql',
                 'panel_image': 'ghcr.io/pterodactyl/panel@sha256:' + 'a' * 64}
        self.installer.save_panel(state)
        self.installer.prepare_mysql_client(state)
        plugin = self.paths.data / 'mysql-plugins/caching_sha2_password.so'
        self.assertEqual(state['mysql_plugin_sha256'], checksum(plugin))
        count = lambda: sum(args[:2] == ['docker', 'run'] for args, _ in self.runner.calls)
        self.assertEqual(count(), 1)
        self.installer.prepare_mysql_client(state)
        self.assertEqual(count(), 1)
        plugin.write_bytes(b'corrupt plugin')
        self.installer.prepare_mysql_client(state)
        self.assertEqual(count(), 2)
        self.assertEqual(state['mysql_plugin_sha256'], checksum(plugin))
        volumes = self.installer.compose_config(state)['services']['panel']['volumes']
        self.assertTrue(any(v.get('target') == '/usr/lib/mariadb/plugin' and v['read_only'] for v in volumes))
