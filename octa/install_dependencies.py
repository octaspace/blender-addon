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
import site


def redraw_preferences():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "PREFERENCES":
                area.tag_redraw()


def handle_windows_permission_error(e, operator, description) -> bool:
    """
    Detect if the error is a Windows "Access is denied" error ([Error 5]).
    If so, show a Blender error message instructing the user to run Blender as Administrator,
    end the operator, and return True. Otherwise, return False.
    """
    if sys.platform.startswith("win") and (
        "Access is denied" in str(e) or "[Error 5]" in str(e)
    ):
        msg = "Windows Access Denied. Please run Blender as Administrator."
        print(msg)
        # Report the error to Blender's UI
        operator.report({"ERROR"}, msg)
        operator.set_progress_name(msg)
        operator.finish(bpy.context)
        operator.set_progress(1)
        operator._set_running(False)
        return True
    return False


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
                "Warning: importlib.metadata not available. Cannot check installed packages."
            )
            return [], []

        def normalize_package_name(name):
            return name.lower().replace("-", "_").replace(".", "_")

        if not os.path.isfile(cls.requirements_path):
            print(f"Error: Requirements file not found at {cls.requirements_path}")
            return [], []

        requirements = cls.read_requirements(cls.requirements_path)
        if not requirements:
            print("No requirements found to install.")
            return [], []

        # Get installed packages and versions
        installed_packages = {}
        for dist in distributions():
            try:
                dist_name = dist.metadata.get("Name")
                if dist_name:
                    package_name = normalize_package_name(dist_name)
                    installed_packages[package_name] = dist.version
            except Exception as e:
                print(f"Warning: Error reading package metadata: {e}")

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
                            f"{package_name}=={required_version} (found {installed_version})"
                        )
                else:
                    installed_correctly.append(package_name)
            else:
                missing_or_incorrect.append(package_name)

        return installed_correctly, missing_or_incorrect

    @classmethod
    def get_installed_packages_initialized(cls):
        return cls._installed_packages_initialized

    @classmethod
    def set_installed_packages(cls):
        """Retrieve a dictionary of installed packages and their versions using pip list."""
        python_exe = sys.executable
        try:
            result = subprocess.run(
                [python_exe, "-m", "pip", "list"],
                stdout=subprocess.PIPE,
                text=True,
                check=True,
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
            print("Installed packages updated:", packages)
        except subprocess.CalledProcessError as e:
            print("Error: Failed to retrieve installed packages:", e)
            cls._installed_packages_initialized = False
            cls._installed_packages = {}

    @classmethod
    def get_installed_packages(cls):
        return cls._installed_packages

    @classmethod
    def poll(cls, context):
        return not cls._running

    @classmethod
    def _set_running(cls, value: bool):
        print(f"Setting running state to {value}")
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
        print(f"Progress name: {value}")
        cls._progress_name = value

    @classmethod
    def get_progress_name(cls):
        return cls._progress_name

    @classmethod
    def get_progress_icon(cls):
        return cls._progress_icon

    @classmethod
    def set_progress_icon(cls, value: str):
        print(f"Progress icon: {value}")
        cls._progress_icon = value

    @classmethod
    def read_requirements(cls, file_path):
        if not os.path.exists(file_path):
            print(f"Warning: Requirements file {file_path} does not exist.")
            return []

        try:
            with open(file_path, "r") as file:
                requirements = file.readlines()
            requirements = [req.strip() for req in requirements if req.strip()]
            return requirements
        except Exception as e:
            print(f"Error: Unable to read requirements file: {e}")
            return []

    def modal(self, context, event):
        if event.type == "TIMER":
            if not self.get_running():
                self.finish(context)
                return {"FINISHED"}
        return {"PASS_THROUGH"}

    def cancel(self, context):
        self.report({"INFO"}, "Octa render submit cancelled")
        print("Operation cancelled by user.")

    def invoke(self, context, event):
        if self.get_running():
            print("Operator already running, invocation canceled.")
            return {"CANCELLED"}

        self._set_running(True)

        installed_correctly, missing_or_incorrect = self.check_dependencies_installed()

        if not self.uninstall and not missing_or_incorrect:
            print("All packages are already installed correctly. Nothing to do.")
            self._set_running(False)
            return {"CANCELLED"}

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
        msg = (
            "All packages installed"
            if not self.uninstall
            else "All packages uninstalled"
        )
        self.report({"INFO"}, msg)
        print(msg)

    def async_install(self, requirements, installed_correctly):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.set_progress(0)

        action = "uninstall" if self.uninstall else "install"
        self.set_progress_name(f"Preparing to {action}")
        self.set_progress_icon("SHADERFX" if not self.uninstall else "X")

        # Ensure pip is available
        try:
            ensurepip.bootstrap()
        except Exception as e:
            print("Error: ensurepip bootstrap failed:", e)

        python_exe = sys.executable
        try:
            site_packages_list = site.getsitepackages()
            if not site_packages_list:
                print("Error: No site-packages directory found. Installation may fail.")
                site_packages = ""
            else:
                site_packages = site_packages_list[0]
        except Exception as e:
            print("Error: Unable to retrieve site-packages directory:", e)
            site_packages = ""

        total_requirements = len(requirements)

        async def run_subprocess(cmd, description):
            print(f"Running command for {description}: {' '.join(cmd)}")
            try:
                result = await loop.run_in_executor(
                    None,
                    functools.partial(
                        subprocess.run,
                        cmd,
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    ),
                )
                print(f"Command succeeded for {description}. Output:\n{result.stdout}")
            except subprocess.CalledProcessError as e:
                # First, see if it's a Windows permission error; handle if yes.
                if handle_windows_permission_error(e.stderr, self, description):
                    return  # Stop further processing (we already reported error)
                else:
                    print(f"Command failed ({description}): {e.stderr}")

        async def install_async():
            if not os.path.exists(self.download_directory):
                try:
                    os.makedirs(self.download_directory)
                except Exception as e:
                    print("Error: Unable to create download directory:", e)

            total_tasks = total_requirements * 2
            downloaded_wheels = []

            # Download phase
            for index, req in enumerate(requirements, start=1):
                self.set_progress_name(f"Downloading {req}")
                self.set_progress_icon("IMPORT")

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
                await run_subprocess(download_cmd, f"downloading {req}")
                print(f"Downloaded {req} ({index}/{total_requirements})")

                current_percentage = (index - 1) / total_tasks
                self.set_progress(current_percentage)

                # Attempt to find matching wheels
                normalized_req_name = req.split("==")[0].lower().replace("-", "_")
                wheel_files = [
                    os.path.join(self.download_directory, file)
                    for file in os.listdir(self.download_directory)
                    if file.endswith(".whl") and normalized_req_name in file.lower()
                ]
                if not wheel_files:
                    print(f"Warning: No wheels found for {req} after download.")
                downloaded_wheels.extend(wheel_files)

            # Install phase
            for index, wheel in enumerate(downloaded_wheels, start=1):
                wheel_name = os.path.basename(wheel)
                self.set_progress_name(f"Installing {wheel_name}")
                self.set_progress_icon("DISC")

                install_cmd = [
                    python_exe,
                    "-m",
                    "pip",
                    "install",
                    wheel,
                    "-t",
                    site_packages,
                ]
                await run_subprocess(install_cmd, f"installing {wheel}")
                print(f"Installed {wheel} ({index}/{len(downloaded_wheels)})")

                current_percentage = (total_requirements + index - 1) / total_tasks
                self.set_progress(current_percentage)

            self.set_progress(1)
            self.set_progress_name("All packages installed")
            self.set_progress_icon("SOLO_ON")
            self.set_installed_packages()
            print("All packages installed")

        async def uninstall_async():
            self.set_progress(0)
            self.set_progress_name("Deleting downloaded wheels")
            self.set_progress_icon("TRASH")

            if os.path.exists(self.download_directory):
                try:
                    shutil.rmtree(self.download_directory)
                    print(f"Deleted directory {self.download_directory}")
                except Exception as e:
                    print("Error: Unable to delete wheels directory:", e)

            total_tasks = len(installed_correctly)
            for index, req in enumerate(installed_correctly, start=1):
                self.set_progress_name(f"Uninstalling {req}")
                self.set_progress_icon("UNLINKED")

                uninstall_cmd = [python_exe, "-m", "pip", "uninstall", req, "-y"]
                await run_subprocess(uninstall_cmd, f"uninstalling {req}")
                print(f"Uninstalled {req} ({index}/{total_tasks})")

                current_percentage = index / total_tasks
                self.set_progress(current_percentage)

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
        except Exception as e:
            print(f"Unexpected error during {action}: {e}")
        finally:
            self.finish(bpy.context)
            self.set_progress(1)
            self._set_running(False)
            loop.close()
