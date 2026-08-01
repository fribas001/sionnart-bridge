# Contributing

Contributions should be proposed through GitHub issues and pull requests.

## Development workflow

1. Create a focused branch from `main`.
2. Keep user-visible names consistent with `SionnaRT-Bridge`.
3. Update `CHANGELOG.md` for user-visible behavior changes.
4. Run `pytest` and `python scripts/check_release.py`.
5. Test the extension in Blender 4.5 LTS using **Install from Disk**.
6. For solver changes, compare results with an equivalent native Sionna RT
   script and report numerical tolerances.

## Bug reports

Include the Blender version, operating system, external Python version,
Sionna RT and Mitsuba versions, backend, minimal `.blend` file, log output,
and reproducible steps. Do not upload confidential scene data.

## Licensing

By contributing, you agree that your contribution is distributed under
GPL-3.0-or-later and that you have the right to submit it.
