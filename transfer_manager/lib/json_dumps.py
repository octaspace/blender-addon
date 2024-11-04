import dataclasses
import json


def json_dumps(*args, **kwargs):
    kwargs['cls'] = EnhancedJSONEncoder
    return json.dumps(*args, **kwargs)


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if hasattr(o, 'to_dict'):
            return o.to_dict()
        return super().default(o)
