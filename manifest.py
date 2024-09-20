import toml, sys

version = sys.argv[sys.argv.index("--version") + 1]

if "/" in version:
    version = version.split("/")[0]

print("Updating TOML to version", version)


with open("blender_manifest.toml", "r") as f:
    data = toml.load(f)


with open("blender_manifest.toml", "w") as f:
    data['version'] = version
    toml.dump(data, f)