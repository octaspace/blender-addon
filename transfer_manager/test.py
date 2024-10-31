def test_start():
    import subprocess
    import sys
    import os

    def spawn_detached_process(command):
        if sys.platform.startswith("win"):
            # Windows
            CREATE_NEW_CONSOLE = 0x00000010
            DETACHED_PROCESS = 0x00000008
            return subprocess.Popen(
                command, creationflags=CREATE_NEW_CONSOLE, close_fds=True
            )
        else:
            # Unix-like systems (Linux, macOS)
            return subprocess.Popen(command, preexec_fn=os.setsid, close_fds=True)

    def is_process_running(pid: int):
        if sys.platform.startswith("win"):
            # Windows
            try:
                # Use tasklist command to check if the process is running
                output = subprocess.check_output(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                output = output.decode(errors="ignore")
                if f"{pid}" in output:
                    return True
            except subprocess.CalledProcessError:
                pass
        else:
            # Unix-like systems (Linux, macOS)
            try:
                if sys.platform.startswith("linux"):
                    # Linux
                    os.kill(pid, 0)  # os.kill with signal 0 only checks for existence
                    return True
                else:
                    # macOS
                    output = subprocess.check_output(["ps", "-p", str(pid)])
                    output = output.decode()
                    if f"{pid}" in output:
                        return True
            except (OSError, subprocess.CalledProcessError):
                pass

        return False

    def start_tm():
        process = spawn_detached_process(
            [sys.executable, "-m", "transfer_manager.main"]
        )

        with open("tm.pid", "w") as f:
            f.write(str(process.pid))

    if os.path.isfile("tm.pid"):
        with open("tm.pid", "r") as f:
            pid = f.read()
        if len(pid) < 1 or not is_process_running(int(pid)):
            start_tm()
    else:
        start_tm()


def test_upload():
    import requests
    import os

    requests.post(
        "http://localhost:7780/api/upload",
        json={
            "local_file_path": os.path.abspath("main.py"),
            "job_information": {
                "frame_start": 1,
                "frame_end": 10,
                "batch_size": 1,
                "name": "freds tm test",
                "render_passes": {},
                "render_format": "PNG",
                "render_engine": "cycles",
                "blender_version": "42",
                "blend_name": "test.blend",
                "max_thumbnail_size": 720,
            },
        },
        headers={
            "farm_host": "http://34.147.146.4",
            "api_token": "thisisatestkey",
        },
    )


test_start()

test_upload()
