"""Execute the real Bash bootstrap against a local, recorded GitHub fixture."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from unittest.mock import patch

from test_installer import BaseTest
import installer as app
from ptero.distribution import ensure_language

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
REPOSITORY = "raimondarias/pterodactyl-installer"


def builder():
    spec = importlib.util.spec_from_file_location("language_builder", ROOT / "scripts/build_language_packs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootstrapTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.base = Path(self.temporary.name)
        self.packages = self.base / "languages"
        with contextlib.redirect_stdout(io.StringIO()):
            builder().build(self.packages)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.download_log = self.base / "downloads.jsonl"
        self.work = self.base / "work"
        self.work.mkdir()
        fake = self.bin / "curl"
        fake.write_text("#!" + sys.executable + "\n" + '''
import json, os, pathlib, shutil, sys
args = sys.argv[1:]
url = next(value for value in args if value.startswith('https://'))
target = pathlib.Path(args[args.index('--output') + 1])
with open(os.environ['FIXTURE_LOG'], 'a') as stream:
    stream.write(json.dumps({'url': url, 'args': args}) + '\\n')
if 'api.github.com' in url:
    target.write_text(json.dumps({'sha': 'a' * 40}))
else:
    prefix = 'https://raw.githubusercontent.com/raimondarias/pterodactyl-installer/' + 'a' * 40 + '/languages/'
    if not url.startswith(prefix):
        raise SystemExit(22)
    source = pathlib.Path(os.environ['FIXTURE_PACKAGES']) / url[len(prefix):]
    if not source.is_file():
        raise SystemExit(22)
    shutil.copyfile(source, target)
''')
        fake.chmod(0o755)
        self.environment = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                            "FIXTURE_LOG": str(self.download_log), "FIXTURE_PACKAGES": str(self.packages),
                            "TMPDIR": str(self.work)}
        self.environment.pop("PTERO_SOURCE_REF", None)

    def run_bootstrap(self, selection="", args=("--preview", "--no-animation")):
        return subprocess.run(["bash", str(ROOT / "install.sh"), *args], input=selection,
                              text=True, capture_output=True, env=self.environment, timeout=30)

    def downloads(self):
        return [json.loads(line) for line in self.download_log.read_text().splitlines()] if self.download_log.exists() else []

    def test_first_question_is_english_then_only_selected_language_is_downloaded(self):
        for number, language, text in ((1, "en", "Ready to install"), (2, "es", "Listo para instalar"), (3, "pt-BR", "Pronto para instalar")):
            with self.subTest(language=language):
                self.download_log.unlink(missing_ok=True)
                result = self.run_bootstrap(str(number) + "\n")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Which language would you like to use?", result.stdout)
                self.assertLess(result.stdout.index("Select [1]"), result.stdout.index("GitHub"))
                self.assertIn(text, result.stdout)
                downloads = self.downloads()
                self.assertEqual(len(downloads), 3)
                self.assertTrue(all(f"/{COMMIT}/languages/{language}/" in item["url"] for item in downloads[1:]))
                self.assertEqual(result.stdout.count("Which language would you like to use?"), 1)
                self.assertEqual(list(self.work.iterdir()), [])

    def test_closed_input_does_not_download_anything(self):
        result = self.run_bootstrap("")
        self.assertEqual(result.returncode, 130)
        self.assertEqual(self.downloads(), [])

    def test_invalid_input_reprompts_and_default_selects_english(self):
        result = self.run_bootstrap("invalid\n\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Invalid selection", result.stdout)
        self.assertIn("Ready to install", result.stdout)

    def test_language_flag_skips_selector_and_uses_pinned_commit(self):
        self.environment["PTERO_SOURCE_REF"] = COMMIT
        result = self.run_bootstrap(args=("--language", "es", "--preview", "--no-animation"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Which language", result.stdout)
        self.assertEqual(len(self.downloads()), 2)
        self.assertIn("Listo para instalar", result.stdout)

    def test_invalid_language_or_source_ref_never_downloads_code(self):
        result = self.run_bootstrap(args=("--language", "../es", "--preview"))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.downloads(), [])
        self.environment["PTERO_SOURCE_REF"] = "main/../../other"
        result = self.run_bootstrap("1\n")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.downloads(), [])

    def test_version_and_help_do_not_download_or_ask_questions(self):
        for option in ("--version", "--help"):
            result = self.run_bootstrap(args=(option,))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("Select [1]", result.stdout)
            self.assertEqual(self.downloads(), [])

    def test_missing_unpublished_package_stops_before_running_installer(self):
        (self.packages / "es/installer.tar.gz").unlink()
        result = self.run_bootstrap("2\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No se ejecutó el código", result.stderr)
        self.assertNotIn("Listo para instalar", result.stdout)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_checksum_mismatch_is_rejected_before_extraction(self):
        (self.packages / "es/installer.tar.gz.sha256").write_text("0" * 64 + "  installer.tar.gz\n")
        result = self.run_bootstrap("2\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stderr)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_wrong_language_package_is_rejected(self):
        for filename in ("installer.tar.gz", "installer.tar.gz.sha256"):
            shutil.copyfile(self.packages / "en" / filename, self.packages / "es" / filename)
        result = self.run_bootstrap("2\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match", result.stderr)
        self.assertNotIn("Ready to install", result.stdout)

    def test_traversal_links_devices_and_duplicate_members_are_rejected(self):
        for kind in ("traversal", "absolute", "symlink", "device", "duplicate"):
            with self.subTest(kind=kind):
                archive = self.packages / "en/installer.tar.gz"
                with tarfile.open(archive, "w:gz") as stream:
                    name = "../escaped" if kind == "traversal" else str(self.base / "escaped") if kind == "absolute" else "unsafe"
                    item = tarfile.TarInfo(name)
                    item.size = 0
                    if kind == "symlink":
                        item.type, item.linkname = tarfile.SYMTYPE, str(self.base)
                    elif kind == "device":
                        item.type = tarfile.CHRTYPE
                    stream.addfile(item, io.BytesIO())
                    if kind == "duplicate":
                        stream.addfile(item, io.BytesIO())
                checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
                Path(str(archive) + ".sha256").write_text(checksum + "  installer.tar.gz\n")
                result = self.run_bootstrap("1\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Unsafe or duplicate", result.stderr)
                self.assertFalse((self.base / "escaped").exists())
                self.assertEqual(list(self.work.iterdir()), [])

    def test_language_packages_are_reproducible_and_contain_only_selected_locale(self):
        with contextlib.redirect_stdout(io.StringIO()):
            builder().build(self.base / "second")
        for language in ("en", "es", "pt-BR"):
            archive = self.packages / language / "installer.tar.gz"
            self.assertEqual(archive.read_bytes(), (self.base / "second" / language / archive.name).read_bytes())
            with tarfile.open(archive) as stream:
                catalogue = json.load(stream.extractfile("ptero/locales/messages.json"))
                self.assertTrue(all(set(values) == {language} for values in catalogue.values()))
                self.assertNotIn("tests/test_distribution.py", stream.getnames())
                self.assertIn("ptero/native.py", stream.getnames())

    def test_committed_packages_match_shared_source_and_translation_tables(self):
        for language in ("en", "es", "pt-BR"):
            for filename in ("installer.tar.gz", "installer.tar.gz.sha256", "messages.json", "manifest.json", "README.md"):
                self.assertEqual((ROOT / "languages" / language / filename).read_bytes(),
                                 (self.packages / language / filename).read_bytes(),
                                 "Rebuild language packs: " + language + "/" + filename)


class LanguageChangeTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.directory = Path(self.temporary.name) / "ptero"
        (self.directory / "locales").mkdir(parents=True)
        self.original = {"Choose an option": {"en": "Choose an option"}}
        self.translated = json.dumps({"Choose an option": {"es": "Elige una opción"}}).encode()
        self.target = self.directory / "locales/messages.json"
        self.target.write_text(json.dumps(self.original))
        self.metadata = {"repository": REPOSITORY, "locale_sha256": {"es": hashlib.sha256(self.translated).hexdigest()}}
        (self.directory / "distribution.json").write_text(json.dumps(self.metadata))

    def test_switch_downloads_only_requested_locale_from_same_commit_and_caches_it(self):
        with patch.dict(os.environ, {"PTERO_SOURCE_REF": COMMIT}), patch("ptero.distribution.urllib.request.urlopen", return_value=io.BytesIO(self.translated)) as request:
            updated = ensure_language(self.original, "es", self.directory)
        self.assertIn(f"/{COMMIT}/languages/es/messages.json", request.call_args.args[0].full_url)
        self.assertEqual(updated["Choose an option"]["es"], "Elige una opción")
        self.assertEqual(updated["Choose an option"]["en"], "Choose an option")
        self.assertEqual(json.loads(self.target.read_text()), updated)
        with patch("ptero.distribution.urllib.request.urlopen") as request:
            self.assertEqual(ensure_language(updated, "en", self.directory), updated)
            self.assertEqual(ensure_language(updated, "es", self.directory), updated)
        request.assert_not_called()

    def test_bad_hash_or_failed_download_preserves_existing_catalogue(self):
        for failure in (b"corrupted", OSError("offline")):
            kwargs = {"side_effect": failure} if isinstance(failure, OSError) else {"return_value": io.BytesIO(failure)}
            with patch.dict(os.environ, {"PTERO_SOURCE_REF": COMMIT}), patch("ptero.distribution.urllib.request.urlopen", **kwargs):
                with self.assertRaises(app.InstallerError):
                    ensure_language(self.original, "es", self.directory)
            self.assertEqual(json.loads(self.target.read_text()), self.original)

    def test_source_catalogue_needs_no_network_for_any_language(self):
        catalogue = json.loads((ROOT / "ptero/locales/messages.json").read_text())
        with patch("ptero.distribution.urllib.request.urlopen") as request:
            for language in ("en", "es", "pt-BR"):
                ensure_language(catalogue, language)
        request.assert_not_called()

    def test_language_switch_requires_a_pinned_source(self):
        with patch.dict(os.environ, {"PTERO_SOURCE_REF": "main"}):
            with self.assertRaises(app.InstallerError):
                ensure_language(self.original, "es", self.directory)
