# Photo-Sorter

A modernized, cross-platform replica of [claude-photo-sorter](https://github.com/kairothq/claude-photo-sorter): point it at a camera roll, it sorts photos and videos into folders, finds duplicates, and shows it happening on a local dashboard.

Design and implementation plans live in [`docs/superpowers/`](docs/superpowers/).

**Status:** the core engine is complete — scanning, duplicate detection, contact sheets, the Claude labeller, folder building, the demo roll and the command-line interface are all built and tested. The local web server is underway: it answers `/api/state` and binds to loopback only. The dashboard is specified but not yet built. 251 tests pass.
