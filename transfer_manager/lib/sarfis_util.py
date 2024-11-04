import inspect
import base64


def _run_method(method_data: str, method_name: str, args_data: str, **raw_args: dict):
    import sys
    import os
    venv = os.environ.get('VIRTUAL_ENV')
    if venv is not None:
        sys.path.append(os.path.join(venv, 'lib', 'site-packages'))
    import base64
    method_source = base64.b64decode(method_data).decode()
    args = eval(base64.b64decode(args_data).decode())
    for k, v in raw_args.items():
        args[k[1:]] = v
    args_list: list = [None] * len(args)
    for k, v in args.items():
        args_list[int(k)] = repr(v)
    exec(method_source + "\n" + method_name + "(" + ','.join(args_list) + ")")


def get_call_to_method_with_args(method, args: dict, raw_args: dict) -> str:
    method_data = base64.b64encode(inspect.getsource(method).encode()).decode()
    method_name = method.__name__
    args_data = base64.b64encode(repr(args).encode()).decode()

    run_method_source = inspect.getsource(_run_method)
    kwargs = ''.join([f', _{k}={repr(v)}' for k, v in raw_args.items()])
    run_method_call = f'{_run_method.__name__}({repr(method_data)},{repr(method_name)},{repr(args_data)}'
    if len(kwargs) > 0:
        run_method_call += kwargs
    run_method_call += ")"

    # use the _run_method to unpack it and stuff it into exec
    return run_method_source + run_method_call
