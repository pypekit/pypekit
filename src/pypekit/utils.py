"""pypekit.utils
================
Utility functions for pypekit.
"""

import hashlib
import json
import pickle
from typing import Any


def _stable_hash(obj: Any) -> str:
    """
    Generate a deterministic SHA-256-based hash for an arbitrary Python object.

    The function attempts three strategies, in order of increasing cost, and
    returns as soon as one succeeds:

    1. Use the built-in :pyfunc:`hash`.
    2. JSON-serialise the object with sorted keys to obtain a stable byte
       representation.
    3. Pickle the object with protocol 5.

    For strategies 2 and 3 the resulting byte blob is fed to
    :pyfunc:`hashlib.sha256`, and the digest is returned as a hexadecimal
    string.

    Parameters
    ----------
    obj : Any
        The Python object to hash. May be hashable or unhashable; unhashable
        objects (e.g., lists, dictionaries, custom classes) are handled via
        serialisation.

    Returns
    -------
    str
        A hexadecimal string representing the SHA-256 hash of the object.
    """
    try:
        return str(hash(obj))
    except TypeError:
        pass

    try:
        blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, OverflowError):
        blob = pickle.dumps(obj, protocol=5)

    return hashlib.sha256(blob).hexdigest()
