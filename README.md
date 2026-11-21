# Photo-Sorter

A modernized, cross-platform replica of [claude-photo-sorter](https://github.com/kairothq/claude-photo-sorter): point it at a camera roll, it sorts photos and videos into folders, finds duplicates, and shows it happening on a local dashboard.

Design and implementation plans live in [`docs/superpowers/`](docs/superpowers/).

**Status:** the core engine is nearly complete — scanning, duplicate detection, contact sheets, the Claude labeller, folder building and the demo roll are all built and tested (181 tests). The command-line interface is the last piece. The local web server and the dashboard are specified but not yet built.
