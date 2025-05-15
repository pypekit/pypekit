import hashlib
import json
import pickle
from typing import Any


def _stable_hash(obj: Any) -> str:
    try:
        return str(hash(obj))
    except TypeError:
        pass

    try:
        blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, OverflowError):
        blob = pickle.dumps(obj, protocol=5)

    return hashlib.sha256(blob).hexdigest()