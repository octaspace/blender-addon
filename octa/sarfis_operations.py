import os

import bpy
from .sarfis_util import get_call_to_method_with_args


def ffmpeg():
    return {
        "operation": "exe",
        "arguments": {
            "input": "{node_ffmpeg}",
        },
        "variables": [
            "-framerate",
            "30",
            "-an",
            "-i",
            "{job_input}/%4d.png",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "baseline",
            "-level",
            "3",
            "-f",
            "mp4",
            "{node_folder}/{job_id}/video.mp4",
        ],
    }


def download_unzip(zip_hash: str):
    return {
        "operation": "exe",
        "arguments": {"input": "python", "one_shot": True},
        "variables": [
            "assets/scripts/files/unzip.py",
            "--zip",
            "{node_folder}/{job_id}/input/package.zip",
            "--extract-folder",
            "{node_folder}/{job_id}/input/",
            "--url",
            "https://render-data.octa.computer/{job_id}/input/package.zip",
            "--hash",
            zip_hash,
        ],
    }


def blender(blend_file_name, render_format="PNG", frame_step=1):
    frame_start_string = "{job_start + (node_task-job_start) * job_batch_size}"
    frame_end_string = "{job_start + (node_task-job_start+1) * job_batch_size - 1}"

    if frame_step > 1:
        # frame_start_string = "{job_start + (node_task-job_start * job_frame_step)}"
        frame_start_string = "{job_start + ((node_task - job_start) * job_frame_step)}"

        frame_end_string = frame_start_string

    return {
        "operation": "exe",
        "arguments": {"input": '{eval(f"node_{job_blender_version}")}'},
        "variables": [
            "-b",
            "{node_folder}/{job_id}/input/" + blend_file_name,
            "-y",
            "-s",
            frame_start_string,
            "-e",
            frame_end_string,
            "-F",
            render_format,
            "-o",
            '{node_folder}/{job_id}/{str(node_gpu_index).replace(",", "_")}/output/',
            "-P",
            "/srv/sarfis-pro-node/assets/scripts/blender/octa.py",  # needs to be absolute path
            "-a",
            "--",
            "-enable_devices",
            '[{str(node_gpu_index).replace(",", "_")}]',
            # "{print(frame_start)}",
        ],
    }


def thumbnails(max_size=1024):
    return {
        "operation": "exe",
        "arguments": {"input": "python"},
        "variables": [
            "assets/scripts/files/thumbnails.py",
            "-path",
            '{node_folder}/{job_id}/{str(node_gpu_index).replace(",", "_")}/output/',
            "-size",
            str(max_size),
        ],
    }


def s3_upload():
    node = {
        "operation": "exe",
        "arguments": {"input": "python"},
        "variables": [
            "assets/scripts/files/s3_upload.py",
            "-folder",
            '{node_folder}/{job_id}/{str(node_gpu_index).replace(",", "_")}/output/',
            "-remote_folder",
            "{job_id}/output/",
            "-bucket",
            "octa-render",
            "-remove_files",
        ],
    }
    return node


def print_input_folder_func(folder):
    import os

    single_indent = "  "
    for root, dirs, files in os.walk(folder):
        level = root.replace(folder, "").count(os.sep)
        indent = single_indent * level
        print(f"{indent}{os.path.basename(root)}/")
        subindent = indent + single_indent
        for f in files:
            print(f"{subindent}-{f}")


def print_input_folder():
    return {
        "operation": "exe",
        "arguments": {"input": "python"},
        "variables": [
            "-c",
            get_call_to_method_with_args(
                print_input_folder_func,
                args={},
                raw_args={0: "{node_folder}/{job_id}/input/"},
            ),
        ],
    }


def get_operations(
    blend_file_name, render_format, max_thumbnail_size, zip_hash, frame_step
):
    return [
        download_unzip(zip_hash),
        print_input_folder(),
        blender(
            blend_file_name=blend_file_name,
            render_format=render_format,
            frame_step=frame_step,
        ),
        thumbnails(max_size=max_thumbnail_size),
        s3_upload(),
    ]
