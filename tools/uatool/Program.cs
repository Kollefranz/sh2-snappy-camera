using System.Globalization;
using System.Text.RegularExpressions;
using UAssetAPI;
using UAssetAPI.ExportTypes;
using UAssetAPI.PropertyTypes.Objects;
using UAssetAPI.PropertyTypes.Structs;
using UAssetAPI.UnrealTypes;
using UAssetAPI.Unversioned;

// uatool <usmap> <asset.uasset> [--filter regex] [--set name=value]... [--add name=value]... [--skip pathSubstring] [--out file]
// Without --out it only prints float properties matching --filter. --set changes every float with that name
// (except paths containing --skip); --add appends a float to Default__ exports that lack it.
CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

if (args.Length < 2) { Console.Error.WriteLine("usage: uatool <usmap> <asset.uasset> [options]"); return 2; }

var filter = new Regex("Rotation|Interp|InputScale|Lag", RegexOptions.IgnoreCase);
var sets = new Dictionary<string, float>();
var adds = new Dictionary<string, float>();
string? skip = null, outPath = null;
for (int i = 2; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--filter": filter = new Regex(args[++i], RegexOptions.IgnoreCase); break;
        case "--set": { var kv = args[++i].Split('='); sets[kv[0]] = float.Parse(kv[1], CultureInfo.InvariantCulture); break; }
        case "--add": { var kv = args[++i].Split('='); adds[kv[0]] = float.Parse(kv[1], CultureInfo.InvariantCulture); break; }
        case "--skip": skip = args[++i]; break;
        case "--out": outPath = args[++i]; break;
        default: Console.Error.WriteLine($"unknown option {args[i]}"); return 2;
    }
}

var asset = new UAsset(args[1], EngineVersion.VER_UE5_1, new Usmap(args[0]));
int changed = 0;

void Walk(IEnumerable<PropertyData> props, string path, string exp)
{
    foreach (var p in props)
    {
        var name = p.Name.ToString();
        switch (p)
        {
            case FloatPropertyData f:
                if (filter.IsMatch(name)) Console.WriteLine($"{exp} :: {path}{name} = {f.Value}");
                if (sets.TryGetValue(name, out var nv) && !(skip != null && path.Contains(skip)))
                {
                    f.Value = nv; changed++;
                    Console.WriteLine($"   SET {exp} :: {path}{name} -> {nv}");
                }
                break;
            case StructPropertyData s: Walk(s.Value, path + name + ".", exp); break;
            case ArrayPropertyData a:
                for (int i = 0; i < a.Value.Length; i++)
                    if (a.Value[i] is StructPropertyData sp) Walk(sp.Value, $"{path}{name}[{i}].", exp);
                break;
            case MapPropertyData m:
                foreach (var kv in m.Value)
                    if (kv.Value is StructPropertyData sp) Walk(sp.Value, $"{path}{name}[{kv.Key}].", exp);
                break;
        }
    }
}

foreach (var e in asset.Exports)
    if (e is NormalExport ne && ne.Data.Count > 0) Walk(ne.Data, "", e.ObjectName.ToString());

foreach (var e in asset.Exports)
    if (e is NormalExport ne && ne.ObjectName.ToString().StartsWith("Default__"))
        foreach (var kv in adds)
            if (!ne.Data.Any(p => p.Name.ToString() == kv.Key))
            {
                ne.Data.Add(new FloatPropertyData(new FName(asset, kv.Key)) { Value = kv.Value });
                changed++;
                Console.WriteLine($"   ADD {ne.ObjectName} :: {kv.Key} = {kv.Value}");
            }

if (outPath != null)
{
    asset.Write(outPath);
    Console.WriteLine($"wrote {outPath}, {changed} values changed");
}
return 0;
