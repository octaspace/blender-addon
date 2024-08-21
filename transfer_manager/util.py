import uuid


def get_next_id() -> str:
    return str(uuid.uuid4())  # TODO: replace with uuid7 once it is added to python because they are sortable by timestamp
