# Tooling notes

`build.py` needs three external things. None are bundled.

## retoc

Download `retoc_cli-x86_64-pc-windows-msvc.zip` from <https://github.com/trumank/retoc/releases> (tested with v0.1.5),
check the `.sha256` next to it, and point `paths.retoc` in `config.local.json` at `retoc.exe`.
Keep the path short: Windows refuses to start executables whose path exceeds 260 characters.

## SH2 .usmap

The stock assets use Unreal's unversioned properties, so reading them needs the game's reflection data:

1. Install UE4SS into `SHProto\Binaries\Win64` (copy `dwmapi.dll` and the `ue4ss` folder from an experimental release;
   set `GuiConsoleEnabled = 1` in `UE4SS-settings.ini`).
2. Launch the game, load a save.
3. In the UE4SS window: **Dumpers → Generate .usmap file**. The `.usmap` appears in `Win64\ue4ss\`.
4. Point `paths.usmap` at it. A `.usmap` is tied to the game build (tested with Steam build 17080069, UE 5.1).

You can remove UE4SS afterwards; the finished mod does not need it. (Lua scripts polling the camera every frame crashed the
game during development, so the mod deliberately contains no scripts.)

## uatool

`tools/uatool/` is a tiny console app on top of UAssetAPI (restored from NuGet on first build).

```
dotnet tools/uatool/out/uatool.dll <usmap> <asset.uasset> --filter "Lag|Interp"     # print matching floats
dotnet tools/uatool/out/uatool.dll <usmap> <asset.uasset> --set RotationLag=1000 --out patched.uasset
```

Reading a stock asset and writing it back unchanged is byte-identical, so edits only touch what you ask for.

## Updating for a new game build

Regenerate the `.usmap`, rerun `python tools/build.py`. If a property was renamed, `build.py` fails at the verify step
instead of silently shipping a mod that does nothing.
