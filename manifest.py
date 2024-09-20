import toml, sys, json, hashlib

version = sys.argv[sys.argv.index("--version") + 1]
version = version.split("/")[-1] if "/" in version else version

with open("/tmp/OctaRender.zip", "rb") as archive:
    archive_content = archive.read()

with open("blender_manifest.toml", "r+") as f:
    manifest = toml.load(f)
    manifest['version'] = version
    toml.dump(manifest, f)

with open("blender_index.json", "r+") as f:
    index = json.load(f)
    index['data'][0]['version'] = version
    index['data'][0]['archive_url'] = f"https://github.com/octaspace/blender-addon/releases/download/{version}/OctaRender.zip"
    index['data'][0]['archive_size'] = len(archive_content)
    index['data'][0]['archive_hash'] = f"sha256:{hashlib.sha256(archive_content).hexdigest()}"
    json.dump(index, f, indent=4)
