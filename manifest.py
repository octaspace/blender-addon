import toml, sys, json, hashlib, zipfile, os

version = sys.argv[sys.argv.index("--version") + 1]
version = version.split("/")[-1] if "/" in version else version

addon_directory = "/tmp/OctaRender"
exclude_files = ["__pycache__",
                 ".git",
                 ".github",
                 ".gitignore",
                 ".gitattributes",
                 ".github",
                 "README.md",
                 "extensions_index.json",
                 "manifest.py",                 
                 "update_manifest.py"]

with open(os.path.join(addon_directory, "blender_manifest.toml"), "r+") as f:
    manifest = toml.load(f)
    manifest['version'] = version
    toml.dump(manifest, f)

with zipfile.ZipFile(f"{addon_directory}.zip", "w") as zip_archive:
    for root, dirs, files in os.walk(addon_directory):
        for file in files:
            if file not in exclude_files:
                zip_archive.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), '/tmp/'))

with open(f"{addon_directory}.zip", "rb") as archive:
    archive_content = archive.read()

with open(os.path.join(addon_directory, "extensions_index.json"), "r+") as f:
    index = json.load(f)
    index['data'][0]['version'] = version
    index['data'][0]['archive_url'] = f"https://github.com/octaspace/blender-addon/releases/download/{version}/OctaRender.zip"
    index['data'][0]['archive_size'] = len(archive_content)
    index['data'][0]['archive_hash'] = f"sha256:{hashlib.sha256(archive_content).hexdigest()}"
    json.dump(index, f, indent=4)




