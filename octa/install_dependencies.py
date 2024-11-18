import bpy
import ensurepip
import os
import asyncio
import subprocess
import sys
from threading import Thread
import re
import shutil
import functools


def redraw_preferences():
    print("redraw_preferences")
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "PREFERENCES":
                area.tag_redraw()


class InstallDependenciesOperator(bpy.types.Operator):
    """Install Python dependencies from a requirements.txt file."""

    bl_idname = "wm.install_dependencies"
    bl_label = "Install Python Dependencies"
    _timer = None
    _running = False
    _progress = 0
    _progress_name = ""
    _progress_icon = "NONE"

    _installed_packages_initialized = False
    _installed_packages = {}

    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_of_parent_dir = os.path.abspath(os.path.join(script_dir, os.pardir))

    requirements_path = os.path.join(parent_of_parent_dir, "requirements.txt")
    download_directory = os.path.join(parent_of_parent_dir, "wheels")

    uninstall: bpy.props.BoolProperty(name="Uninstall", default=False)

    def __init__(self):
        self._run_thread: Thread = None

    @classmethod
    def check_dependencies_installed(cls):
        """Check which packages from requirements.txt are installed and which are missing."""
        try:
            from importlib.metadata import distributions
        except ImportError:
            print(
                "importlib.metadata is not available. Cannot check installed packages."
            )
            return [], []

        def normalize_package_name(name):
            return name.lower().replace("-", "_").replace(".", "_")

        # Get installed packages and versions
        installed_packages = {}
        for dist in distributions():
            package_name = normalize_package_name(dist.metadata["Name"])
            installed_packages[package_name] = dist.version

        requirements = cls.read_requirements(cls.requirements_path)

        installed_correctly = []
        missing_or_incorrect = []

        for requirement in requirements:
            package_name, _, required_version = requirement.partition("==")
            package_name = package_name.strip()
            normalized_name = normalize_package_name(package_name)

            installed_version = installed_packages.get(normalized_name)

            if installed_version:
                if required_version:
                    if installed_version == required_version:
                        installed_correctly.append(
                            f"{package_name}=={installed_version}"
                        )
                    else:
                        missing_or_incorrect.append(
                            f"{package_name}=={required_version} "
                            f"(found version {installed_version})"
                        )
                else:
                    installed_correctly.append(package_name)
            else:
                missing_or_incorrect.append(package_name)

        if missing_or_incorrect:
            print("Missing or Incorrectly Versioned Packages:", missing_or_incorrect)
        if installed_correctly:
            print("Correctly Installed Packages:", installed_correctly)

        return installed_correctly, missing_or_incorrect

    @classmethod
    def get_installed_packages_initialized(cls):
        return cls._installed_packages_initialized

    @classmethod
    def set_installed_packages(cls):
        """Retrieve a dictionary of installed packages and their versions using pip list."""
        python_exe = sys.executable
        result = subprocess.run(
            [python_exe, "-m", "pip", "list"], stdout=subprocess.PIPE, text=True
        )
        packages = {}
        for line in result.stdout.splitlines():
            if "Package" in line and "Version" in line:
                continue
            match = re.match(r"(\S+)\s+(\S+)", line)
            if match:
                packages[match.group(1)] = match.group(2)

        cls._installed_packages_initialized = True
        cls._installed_packages = packages

    @classmethod
    def get_installed_packages(cls):
        return cls._installed_packages

    @classmethod
    def poll(cls, context):
        return not cls._running

    @classmethod
    def _set_running(cls, value: bool):
        cls._running = value

    @classmethod
    def get_running(cls) -> bool:
        return cls._running

    @classmethod
    def get_progress(cls):
        return cls._progress

    @classmethod
    def set_progress(cls, value: float):
        cls._progress = value
        redraw_preferences()

    @classmethod
    def set_progress_name(cls, value: str):
        cls._progress_name = value

    @classmethod
    def get_progress_name(cls):
        return cls._progress_name

    @classmethod
    def get_progress_icon(cls):
        return cls._progress_icon

    @classmethod
    def set_progress_icon(cls, value: str):
        cls._progress_icon = value

    @classmethod
    def read_requirements(cls, file_path):
        with open(file_path, "r") as file:
            requirements = file.readlines()
        requirements = [req.strip() for req in requirements if req.strip()]
        return requirements

    def modal(self, context, event):
        if event.type == "TIMER":
            if not self.get_running():
                self.finish(context)
                return {"FINISHED"}

        return {"PASS_THROUGH"}

    def cancel(self, context):
        self.report({"INFO"}, "Octa render submit cancelled")

    def invoke(self, context, event):
        if self.get_running():
            return {"CANCELLED"}

        self._set_running(True)

        installed_correctly, missing_or_incorrect = self.check_dependencies_installed()

        self.packages_to_install = missing_or_incorrect
        self._run_thread = Thread(
            target=self.async_install,
            args=(self.packages_to_install, installed_correctly),
        )
        self._run_thread.start()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def finish(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None
        self._run_thread = None
        self._set_running(False)
        self.report({"INFO"}, "All packages installed")

    def async_install(self, requirements, installed_correctly):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.set_progress(0)

        self.set_progress_name(
            "Preparing to install" if not self.uninstall else "Preparing to uninstall"
        )
        self.set_progress_icon("SHADERFX" if not self.uninstall else "X")

        ensurepip.bootstrap()
        python_exe = sys.executable
        site_packages = os.path.join(os.path.dirname(python_exe), "Lib", "site-packages")
        total_requirements = len(requirements)

        async def install_async():
            if not os.path.exists(self.download_directory):
                os.makedirs(self.download_directory)

            total_requirements = len(requirements)
            total_tasks = total_requirements * 2

            downloaded_wheels = []
            for index, req in enumerate(requirements, start=1):
                download_cmd = [
                    python_exe,
                    "-m",
                    "pip",
                    "download",
                    "--only-binary=:all:",
                    "-d",
                    self.download_directory,
                    req,
                ]
                await loop.run_in_executor(None, subprocess.run, download_cmd)
                print(f"Downloaded {req} ({index}/{total_requirements})")

                current_percentage = (index - 1) / total_tasks
                self.set_progress(current_percentage)
                self.set_progress_name(f"Downloading {req}")
                self.set_progress_icon("IMPORT")

                wheel_files = [
                    os.path.join(self.download_directory, file)
                    for file in os.listdir(self.download_directory)
                    if file.endswith(".whl") and req.split("==")[0] in file
                ]
                downloaded_wheels.extend(wheel_files)

            for index, wheel in enumerate(downloaded_wheels, start=1):
                install_cmd = [python_exe, "-m", "pip", "install", wheel, "-t", site_packages]
                await loop.run_in_executor(None, subprocess.run, install_cmd)
                print(f"Installed {wheel} ({index}/{len(downloaded_wheels)})")

                current_percentage = (total_requirements + index - 1) / total_tasks
                self.set_progress(current_percentage)
                self.set_progress_name(f"Installing {os.path.basename(wheel)}")
                self.set_progress_icon("DISC")

            self.set_progress(1)
            self.set_progress_name("All packages installed")
            self.set_progress_icon("SOLO_ON")
            self.set_installed_packages()
            print("All packages installed")

        async def uninstall_async():
            self.set_progress(0)
            self.set_progress_name("Deleting downloaded wheels")
            self.set_progress_icon("TRASH")

            total_tasks = len(installed_correctly)
            if os.path.exists(self.download_directory):
                shutil.rmtree(self.download_directory)

            for index, req in enumerate(installed_correctly, start=1):
                uninstall_cmd = [python_exe, "-m", "pip", "uninstall", req, "-y"]
                await loop.run_in_executor(None, subprocess.run, uninstall_cmd)
                print(f"Uninstalled {req} ({index}/{installed_correctly})")

                current_percentage = index / total_tasks
                self.set_progress(current_percentage)
                self.set_progress_name(f"Uninstalling {req}")
                self.set_progress_icon("UNLINKED")

            self.set_progress(1)
            self.set_progress_name("All packages uninstalled")
            self.set_progress_icon("X")
            print("All packages uninstalled")

            self.set_installed_packages()

        try:
            if not self.uninstall:
                loop.run_until_complete(install_async())
            else:
                loop.run_until_complete(uninstall_async())
        finally:
            self.finish(bpy.context)
            self.set_progress(1)
            self._set_running(False)
            loop.close()
