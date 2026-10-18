# SH2 Snappy Camera

> **AI disclaimer:** this project (code, config and docs) was written with AI assistance (Claude Code). Review it before trusting it, and use it at your own risk.

Removes the sluggish, self-accelerating third-person camera in Silent Hill 2 (2024, PC). It is a plain asset override
(no scripts or DLLs) built from [`config.json`](config.json).

Not affiliated with Konami or Bloober Team.

## Install

Copy the three `SH2_SnappyCamera_P.*` files from a release zip into
`...\SILENT HILL 2\SHProto\Content\Paks\~mods` (create `~mods` if needed). Delete them to uninstall.
Not compatible with other mods that edit `ChPlay_CameraProfiles_DA` or `ChPlay_MovementSettings_DA`.

## What it changes

| Asset property | Stock | Mod |
|---|---|---|
| `ChPlay_MovementSettings_DA` → `ControlRotationInterpSpeed` | 2 – 4 | 10000 |
| `ChPlay_CameraProfiles_DA` → `RotationLag` | 14 | 1000 |

Speeds are Unreal interpolation speeds: higher = snappier. Don't use `0`: the camera arm blends lag between profiles, and
mixing `0` with non-zero values passes through near-zero speeds, which freezes the camera for about a second after you move.

Presets in `config.json`: `default`, `reduced-follow-lag` (also shortens positional follow lag), `aiming-experimental` (also aiming/flashlight; untested).

## Build

Needs Python 3.10+, .NET SDK 9+, [retoc](https://github.com/trumank/retoc), your own copy of the game and a `.usmap`
(see [tools/README.md](tools/README.md)).

```bash
cp config.local.example.json config.local.json   # set the three paths
python tools/build.py                            # all presets -> dist/
```

Add a preset by adding an entry under `presets` in `config.json`.

## Credits

[retoc](https://github.com/trumank/retoc) (trumank), [UAssetAPI](https://github.com/atenfyr/UAssetAPI) (atenfyr),
[UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) (UE4SS-RE), and axbhub's First Person FPP Camera Mode mod, whose changelog hinted at where the lag lives.

## License

[MIT](LICENSE). Game assets are not included; the built mod contains modified copies of two small data assets.
