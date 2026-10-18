# Changelog

## 0.9.0 (release candidate)

- First packaged build, generated from `config.json` by `tools/build.py`.
- `default`: look-rotation easing off (movement profiles 2 to 4 → 10000), camera-arm rotation lag 14 → 1000 on every profile.
- `reduced-follow-lag`: `default` + positional follow lag 40 on all profiles.
- `aiming-experimental`: `default` + ranged-weapon aim/reload rotation speed and flashlight rotation speed → 10000.
- Verified by reading each packed mod back; **not yet played through in-game** (bump to 1.0.0 after that).

### Findings that shaped the design

- Setting `RotationLag` to 0 on some profiles makes the camera stick after starting to move (lag speed ramps through
  near-zero values). All profiles now share one high value.
- The spring arm caches copies of the camera profiles at level load, so runtime edits of the data asset are ignored.
  The mod therefore ships as an asset override instead of a script.
