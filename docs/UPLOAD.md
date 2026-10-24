# Publishing and maintaining the project on GitHub

Destination: **raimondarias/pterodactyl-installer**, branch **main**.

Installer version: **1.2.1**. Publish the root bootstrap and generated
language distributions together. Building or testing locally does not update
GitHub; a commit must be pushed to `main` to publish changes.

## Upload the contents, with their paths intact

Extract `pterodactyl-installer-repo.zip` on your computer. Open its
`pterodactyl-installer/` directory and upload **the contents of that directory**
to the root of your GitHub repository. Do not upload the ZIP itself as the
installation, and do not add an extra nested `pterodactyl-installer/` directory
inside the repository.

The root must contain:

```text
install.sh
installer.py
README.md
LICENSE
.gitignore
languages/
  en/
    installer.tar.gz
    installer.tar.gz.sha256
    messages.json
    manifest.json
    README.md
  es/
    (same five files, Spanish distribution)
  pt-BR/
    (same five files, Brazilian Portuguese distribution)
ptero/
scripts/
tests/
docs/
test-results/
```

The README entry point is **install.sh**. The runtime, language folders and
shared source are all maintained in this repository.

Upload each archive and its checksum together. **Commit all three language
folders and the root bootstrap in the same revision.** The bootstrap resolves
one commit and fetches the selected files from it.

## What the user runs

The first README command is:

```bash
curl -fsSL https://raw.githubusercontent.com/raimondarias/pterodactyl-installer/main/install.sh -o ptero-setup.sh && sudo bash ptero-setup.sh
```

Flow:

1. Download the small root `install.sh` bootstrap.
2. Ask **Which language would you like to use?** in English: 1 English,
   2 Español, 3 Português (Brasil); Enter defaults to English.
3. Install missing Python prerequisites after the selection, if necessary.
4. Resolve `main` to its commit SHA through GitHub's API.
5. Download only the selected folder's `installer.tar.gz` and checksum.
6. Verify hash, archive safety, package language, version and repository.
7. Open the actual installer in that language, with no second language question.
8. Collect/review the installation plan and run only the selected operation.

Changing language from the runtime menu fetches just the new `messages.json`
from the same commit and checks the hash embedded in the current package. This
keeps active sessions consistent even if `main` is updated during setup.

## Verify publication without installing services

On a machine that already has Python 3 and curl, download the bootstrap and run:

```bash
bash ptero-setup.sh --preview --no-animation
```

You can also run `python3 tests/published_check.py` for all three actual GitHub
downloads plus verified language changes without installing services.

Choose 1, 2 and 3 in separate runs. Confirm that the first question is in English,
the download path matches the choice and the preview appears in that language.
It must exit with an error if any selected package or checksum is missing.

Before deploying services, complete the clean-VPS procedure in
[TESTING.md](TESTING.md). Local fixtures cannot establish that files were
actually uploaded to your repository.

## Maintain one codebase and three real packages

- Shared functionality lives in `ptero/`. Do not hand-maintain three divergent
  copies of the installer.
- Edit translations in the maintained `scripts/*translations.txt` tables.
- `ptero/locales/messages.json` is the full source catalogue used by local mode.
- Each generated language archive contains the same shared code and **only its
  selected translation catalogue**. It has no other language's translated text
  file and does not fetch the whole repository.
- `languages/*/messages.json`, manifests, archives and checksums are generated
  outputs and should be committed because the online bootstrap downloads them.

After editing code or translations:

```bash
python3 scripts/build_catalog.py
python3 scripts/build_language_packs.py
bash tests/run.sh
python3 scripts/build_release.py
```

Tests fail if the committed language packages are stale compared with shared
source. Rebuilding unchanged inputs produces identical language archive hashes.
When bumping the runtime version, update `ptero/__init__.py` and the bootstrap's
`VERSION` together, then regenerate all packages.

Use `scripts/run_local.sh` for local/offline-code development. The self-contained
`.run` remains available as an alternative containing all three languages; the
README's primary online command uses the selected-folder download flow.
