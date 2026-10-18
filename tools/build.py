#!/usr/bin/env python3
"""Build SH2 Snappy Camera paks from config.json.

Pipeline per preset: retoc to-legacy (stock assets) -> uatool patch -> retoc to-zen -> stub .pak -> verify -> zip.
Needs: retoc, dotnet SDK, an SH2 .usmap, and the game's Paks folder (see tools/README.md).
"""
import argparse, copy, hashlib, json, os, re, shutil, struct, subprocess, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UATOOL_DLL = ROOT / "tools" / "uatool" / "out" / "uatool.dll"

# stock asset name (retoc filter) -> path under the legacy output tree
DATA_ASSETS = {
    "movement": ("ChPlay_MovementSettings_DA", "SHProto/Content/Game/Gameplay/Data/Character/ChPlay_MovementSettings_DA"),
    "camera": ("ChPlay_CameraProfiles_DA", "SHProto/Content/Game/Gameplay/Data/Character/ChPlay_CameraProfiles_DA"),
}
WEAPONS = {
    "WeaponPistol_BP": "SHProto/Content/Game/Gameplay/Weapons/Pistol/WeaponPistol_BP",
    "WeaponRifle_BP": "SHProto/Content/Game/Gameplay/Weapons/Rifle/WeaponRifle_BP",
    "WeaponShotgun_Alt_D_BP": "SHProto/Content/Game/Gameplay/Weapons/Shotgun/WeaponShotgun_Alt_D_BP",
}
FLASHLIGHT = ("Flashlight_BP", "SHProto/Content/Game/Gameplay/Interactions/Items/flashlight/Flashlight_BP")


def die(msg):
    sys.exit(f"error: {msg}")


def run(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        die(f"{' '.join(str(c) for c in cmd[:3])} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def deep_merge(a, b):
    out = copy.deepcopy(a)
    for k, v in b.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def validate(s):
    def need(path, v, lo):
        if v is not None and (not isinstance(v, (int, float)) or v < lo):
            die(f"{path}={v!r} must be null or a number >= {lo} (0/tiny speeds freeze the camera, see config.json notes)")
    need("movement.controlRotationInterpSpeed", s["movement"]["controlRotationInterpSpeed"], 0.5)
    need("camera.rotationLag", s["camera"]["rotationLag"], 50)
    need("camera.forwardLag", s["camera"]["forwardLag"], 1)
    need("camera.nonForwardLag", s["camera"]["nonForwardLag"], 1)
    need("aiming.controlRotationInterpSpeed", s["aiming"]["controlRotationInterpSpeed"], 0.5)
    need("aiming.cameraRotationLag", s["aiming"]["cameraRotationLag"], 50)


def empty_pak():
    # UE pak v11 with zero entries; .utoc/.ucas are what carry the assets, the pak just makes the game mount them
    mount = b"../../../\0"
    path_hash, full_dir = struct.pack("<q", 0), struct.pack("<i", 0)

    def primary(ph_off, fd_off):
        p = struct.pack("<i", len(mount)) + mount + struct.pack("<iQ", 0, 0)
        p += struct.pack("<i", 1) + struct.pack("<qq", ph_off, len(path_hash)) + hashlib.sha1(path_hash).digest()
        p += struct.pack("<i", 1) + struct.pack("<qq", fd_off, len(full_dir)) + hashlib.sha1(full_dir).digest()
        return p + struct.pack("<ii", 0, 0)

    n = len(primary(0, 0))
    pr = primary(n, n + len(path_hash))
    footer = (b"\0" * 17 + struct.pack("<II", 0x5A6F12E1, 11) + struct.pack("<qq", 0, len(pr))
              + hashlib.sha1(pr).digest() + b"\0" * 160)
    return pr + path_hash + full_dir + footer


def plan(s):
    """-> list of (asset rel path, filter name, [uatool args], {prop: expected value})"""
    jobs = []
    mv, cam, aim = s["movement"], s["camera"], s["aiming"]
    if mv["controlRotationInterpSpeed"] is not None:
        v = mv["controlRotationInterpSpeed"]
        name, rel = DATA_ASSETS["movement"]
        jobs.append((rel, name, ["--set", f"ControlRotationInterpSpeed={v}"], {"ControlRotationInterpSpeed": v}))
    sets = {"RotationLag": cam["rotationLag"], "MovementForwardCameraLag": cam["forwardLag"],
            "MovementNonForwardCameraLag": cam["nonForwardLag"]}
    sets = {k: v for k, v in sets.items() if v is not None}
    if sets:
        name, rel = DATA_ASSETS["camera"]
        jobs.append((rel, name, [a for k, v in sets.items() for a in ("--set", f"{k}={v}")], sets))
    if aim["enabled"]:
        v = aim["controlRotationInterpSpeed"]
        for name, rel in WEAPONS.items():
            args = ["--set", f"ControlRotationInterpSpeed={v}", "--set", f"CharacterControlRotationInterpSpeed={v}",
                    "--add", f"CharacterControlRotationInterpSpeed={v}"]
            exp = {"ControlRotationInterpSpeed": v, "CharacterControlRotationInterpSpeed": v}
            if aim["cameraRotationLag"] is not None:
                args += ["--set", f"RotationLag={aim['cameraRotationLag']}"]
                exp["RotationLag"] = aim["cameraRotationLag"]
            jobs.append((rel, name, args, exp))
        name, rel = FLASHLIGHT
        jobs.append((rel, name, ["--set", f"CharacterControlRotationInterpSpeed={v}"], {"CharacterControlRotationInterpSpeed": v}))
    return jobs


def uatool(usmap, asset, *args):
    return run(["dotnet", UATOOL_DLL, usmap, asset, *args])


def ensure_uatool():
    if not UATOOL_DLL.exists():
        print("building uatool (first run, restores UAssetAPI from NuGet)...")
        run(["dotnet", "build", ROOT / "tools" / "uatool", "-c", "Release", "-o", UATOOL_DLL.parent])


def build_preset(cfg, name, paths, out_dir, verify):
    s = deep_merge(cfg["defaults"], cfg["presets"][name])
    validate(s)
    jobs = plan(s)
    if not jobs:
        die(f"preset {name!r} changes nothing")
    mod = f"{cfg['modName']}_P"
    eng = cfg["engineVersion"]
    retoc, usmap, game = paths["retoc"], paths["usmap"], paths["gamePaks"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stock, patched = tmp / "stock", tmp / "patched"
        stock.mkdir(); patched.mkdir()
        for rel, filt, args, _ in jobs:
            run([retoc, "to-legacy", "-f", filt, "--no-shaders", "--no-script-objects", "--version", eng, game, stock])
            src, dst = stock / f"{rel}.uasset", patched / f"{rel}.uasset"
            if not src.exists():
                die(f"stock asset missing after extraction: {rel}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            uatool(usmap, src, *args, "--out", dst)
        pkg = out_dir / name
        if pkg.exists():
            shutil.rmtree(pkg)
        pkg.mkdir(parents=True)
        run([retoc, "to-zen", "--version", eng, patched, pkg / f"{mod}.utoc"])
        (pkg / f"{mod}.pak").write_bytes(empty_pak())
        run([retoc, "verify", pkg / f"{mod}.utoc"])
        if verify:
            check = tmp / "check"
            (check / "paks").mkdir(parents=True)
            for f in ("global.utoc", "global.ucas"):
                shutil.copy(Path(game) / f, check / "paks" / f)
            for f in pkg.glob(f"{mod}.*"):
                shutil.copy(f, check / "paks" / f.name)
            run([retoc, "to-legacy", "--no-shaders", "--version", eng, check / "paks", check / "legacy"])
            for rel, _, _, expected in jobs:
                out = uatool(usmap, check / "legacy" / f"{rel}.uasset", "--filter", "Lag|Interp")
                for prop, want in expected.items():
                    vals = [float(m.group(1)) for m in re.finditer(rf"[.\s]{prop} = (\S+)", out)]
                    if not vals or any(abs(v - want) > 1e-3 for v in vals):
                        die(f"verify failed: {rel} {prop} wanted {want}, got {vals}")
            print(f"  verified {len(jobs)} asset(s) by reading the packed mod back")
    readme = (ROOT / "nexus" / "INSTALL.txt").read_text(encoding="utf-8").replace("{preset}", name).replace("{version}", cfg["version"])
    (pkg / "INSTALL.txt").write_text(readme, encoding="utf-8")
    zip_path = out_dir / f"{cfg['modName']}-{name}-v{cfg['version']}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(pkg.iterdir()):
            z.write(f, f.name)
    print(f"  {zip_path.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", action="append", help="preset name (repeatable); default: all")
    ap.add_argument("--config", default=ROOT / "config.json")
    ap.add_argument("--out", default=ROOT / "dist")
    ap.add_argument("--game"); ap.add_argument("--retoc"); ap.add_argument("--usmap")
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()

    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    local = ROOT / "config.local.json"
    paths = json.loads(local.read_text(encoding="utf-8")).get("paths", {}) if local.exists() else {}
    paths = {"gamePaks": a.game or paths.get("gamePaks"), "retoc": a.retoc or paths.get("retoc") or shutil.which("retoc"),
             "usmap": a.usmap or paths.get("usmap")}
    paths = {k: (str((ROOT / v).resolve()) if v and not Path(v).is_absolute() else v) for k, v in paths.items()}
    for k, v in paths.items():
        if not v or not Path(v).exists():
            die(f"path {k!r} not set or missing ({v!r}); set it in config.local.json or via CLI")
    for need in ("global.utoc", "SHProto-Windows.utoc"):
        if not (Path(paths["gamePaks"]) / need).exists():
            die(f"{need} not found in {paths['gamePaks']}")
    if not shutil.which("dotnet"):
        die("dotnet SDK not found")
    ensure_uatool()
    presets = a.preset or list(cfg["presets"])
    for p in presets:
        if p not in cfg["presets"]:
            die(f"unknown preset {p!r}; have {list(cfg['presets'])}")
        print(f"[{p}]")
        build_preset(cfg, p, paths, Path(a.out), not a.no_verify)


if __name__ == "__main__":
    main()
