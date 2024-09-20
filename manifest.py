import toml, sys, json, hashlib, zipfile, os

version = sys.argv[sys.argv.index("--version") + 1]
version = version.split("/")[-1] if "/" in version else version

addon_directory = "/tmp/OctaRender"
extension_index = os.path.join(addon_directory, "extensions_index.json")
blender_manifest = os.path.join(addon_directory, "blender_manifest.toml")
zip_path = f"{addon_directory}.zip"

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


with open(blender_manifest, "r") as f:
    manifest = toml.loads(f.read())

with open(blender_manifest, "w") as f:
    manifest['version'] = version
    f.write(toml.dumps(manifest))


with zipfile.ZipFile(zip_path, "w") as zip_archive:
    for root, dirs, files in os.walk(addon_directory):
        for file in files:
            file_path = os.path.join(root, file)
            if any(excluded_file in file_path for excluded_file in exclude_files):
                continue
            else:
                zip_archive.write(file_path, os.path.relpath(file_path, '/tmp/'))


with open(zip_path, "rb") as f:
    archive_content = f.read()

with open(extension_index, "r") as f:
    index = json.loads(f.read())

with open(extension_index, "w") as f:
    index['data'][0]['version'] = version
    index['data'][0]['archive_url'] = f"https://github.com/octaspace/blender-addon/releases/download/{version}/OctaRender.zip"
    index['data'][0]['archive_size'] = len(archive_content)
    index['data'][0]['archive_hash'] = f"sha256:{hashlib.sha256(archive_content).hexdigest()}"
    f.write(json.dumps(index, indent=4))




