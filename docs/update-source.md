# Remote update source

The static update feed is built from the deployable `music_box/` PyMakr
project and published through GitHub Pages. Test projects, tools, PyMakr
configuration, Python caches, and repository files are not published.

## Publishing an application version

1. Finish and commit the application changes.
2. Change `version` in `update_source.json` in the same commit.
3. Push the commit to `main`.
4. Confirm that the **Publish update source** workflow succeeds.

Changing application files without changing `update_source.json` does not
publish them. This prevents an existing version from changing accidentally.
The workflow can also be run manually from the Actions tab when a deployment
needs to be retried.

The MCU will eventually check this stable descriptor URL:

```text
https://silentsammy.github.io/music_box/update.json
```

That descriptor identifies the current version and its versioned manifest.
The manifest lists every deployable file with its exact byte count, SHA-256
hash, and download URL.

## Local preview

Run:

```powershell
python tools/build_update_source.py
```

The generated feed is written to `build/update-source/`, which is ignored by
Git. Building it again safely replaces only a directory previously created by
the same tool.

## One-time GitHub Pages setting

In the GitHub repository, open **Settings → Pages** and select
**GitHub Actions** as the publishing source. GitHub requires this repository
setting before a custom Pages deployment can run.
