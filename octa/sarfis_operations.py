import bpy


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
            "{node_folder}/{job_id}/video.mp4"
        ]
    }


def download_unzip():
    return {
        'operation': 'exe',
        'arguments': {'input': 'python', "one_shot": True},
        'variables': [
            'assets/scripts/files/unzip.py',
            '-zip',
            '{node_folder}/{job_id}/input/package.zip',
            '-folder',
            '{node_folder}/{job_id}/input/',
            '-url',
            'https://render-data.octa.computer/{job_id}/input/package.zip',
        ]
    }


def blender41_exe(blend_file_name, render_format="PNG"):
    return {
        'operation': 'exe',
        'arguments': {'input': '{node_blender41}'},
        'variables': [
            '-b',
            '{node_folder}/{job_id}/input/' + blend_file_name,
            '-y',
            '-s',
            '{job_start + (node_task-job_start) * job_batch_size}',
            '-e',
            '{job_start + (node_task-job_start+1) * job_batch_size - 1}',
            '-F',
            render_format,
            '-o',
            '{node_folder}/{job_id}/{str(node_gpu_index).replace(",", "_")}/output/',
            '-P',
            '/srv/sarfis-pro-node/assets/scripts/blender/octa.py',  # needs to be absolute path
            '-a',
            '--',
            '-enable_devices',
            '[{str(node_gpu_index).replace(",", "_")}]',
        ]
    }


def blender40_exe(blend_file_name, render_format="PNG"):
    return {
        'operation': 'exe',
        'arguments': {'input': 'blender'},
        'variables': [
            '-b',
            '{node_folder}/{job_id}/input/' + blend_file_name,
            '-y',
            '-P',
            '/srv/sarfis-pro-node/assets/scripts/blender/octa.py',  # needs to be absolute path
            '-s',
            '{job_start + (node_task-job_start) * job_batch_size}',
            '-e',
            '{job_start + (node_task-job_start+1) * job_batch_size - 1}',
            '-F',
            render_format,
            '-o',
            '{node_folder}/{job_id}/{str(node_gpu_index).replace(",", "_")}/output/',
            '-a',
            '--',
            '-enable_devices',
            '[{node_gpu_index}]',
        ]
    }


def thumbnails(max_size=1024):
    return {
        'operation': 'exe',
        'arguments': {'input': 'python'},
        'variables': [
            'assets/scripts/files/thumbnails.py',
            '-path',
            '{node_folder}/{job_id}/{str(node_gpu_index).replace(",", "_")}/output/',
            '-size',
            str(max_size),
        ]
    }


def s3_upload():
    node = {
        'operation': 'exe',
        'arguments': {'input': 'python'},
        'variables': ['assets/scripts/files/s3_upload.py',
                      '-folder',
                      '{node_folder}/{job_id}/{str(node_gpu_index).replace(",", "_")}/output/',
                      '-remote_folder',
                      '{job_id}/output/',
                      '-bucket',
                      'octa-render',
                      '-remove_files'
                      ]
    }
    return node


def get_operations(blend_file_name, render_format, max_thumbnail_size):
    return [
        download_unzip(),
        blender41_exe(blend_file_name=blend_file_name, render_format=render_format),
        thumbnails(max_size=max_thumbnail_size),
        s3_upload(),
    ]
