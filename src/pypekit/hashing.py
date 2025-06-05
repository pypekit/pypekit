"""pypekit.hashing
================
Utility for obtaining a repeatable SHA-256 digest from *any* Python object.

The public helper :func:`stable_hash` first attempts a fully deterministic
canonica-JSON serialisation.  If that fails (because the object contains
values that JSON cannot express) it falls back to `pickle` and **optionally**
emits a warning.  The returned digest is always prefixed with either
``"json:"`` or ``"pickle:"`` so the two encodings cannot collide.
"""

import hashlib
import json
import pickle
import warnings
from typing import Any, Iterable, Tuple


def _hash_bytes(obj: Any) -> bytes:
    """
    SHA-256 of *obj* serialised with strict JSON.

    Parameters
    ----------
    obj : Any
        A JSON-serialisable Python object already in canonical form.

    Returns
    -------
    bytes
        The 32-byte digest.
    """
    blob = json.dumps(
        obj,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(blob).digest()


def _canon(obj: Any) -> Any:
    """
    Convert *obj* to a fully ordered, JSON-serialisable structure.

    The transformation is *deep* and idempotent; calling it on an object that
    is already in canonical form returns an equivalent representation.

    Parameters
    ----------
    obj : Any
        The input object.

    Returns
    -------
    Any
        A structure composed only of JSON primitives (`str`, `int`, `float`,
        `bool`, `None`) and containers (`list`) that is guaranteed to serialise
        byte-for-byte identically for equal inputs.
    """
    if isinstance(obj, dict):
        items: Iterable[Tuple[Any, Any]] = (
            (_canon(k), _canon(v)) for k, v in obj.items()
        )
        return [list(pair) for pair in sorted(items, key=lambda kv: _hash_bytes(kv[0]))]

    if isinstance(obj, (set, frozenset)):
        return sorted((_canon(x) for x in obj), key=_hash_bytes)

    if isinstance(obj, (list, tuple)):
        return [_canon(x) for x in obj]

    return obj


def stable_hash(obj: Any, *, verbose: bool = False) -> str:
    """
    Deterministic SHA-256 digest of *obj* with explicit namespace.

    The function attempts two serialisation strategies in order:

    1. **Canonical JSON** - provides a digest stable across Python versions,
       platforms, and builds.

    2. **Pickle (protocol 5)** - used only when JSON fails.  This path may
       yield different digests for *equal* objects on different interpreter
       versions or architectures.  When *verbose* is ``True`` a
       :class:`UserWarning` is emitted to highlight the weaker guarantee.

    Parameters
    ----------
    obj : Any
        The object to hash.
    verbose : bool, default ``False``
        If ``True`` and pickle fallback is taken, issue a warning that the
        result is not guaranteed to be stable across Python versions or
        platforms.

    Returns
    -------
    str
        A 64-character hexadecimal digest prefixed with either ``"json:"`` or
        ``"pickle:"`` to indicate which serialisation route was taken.

    Warns
    -----
    UserWarning
        Emitted only when *verbose* is ``True`` **and** the object cannot be
        represented in canonical JSON, so pickle is used instead.
    """
    try:
        blob = json.dumps(
            _canon(obj),
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        prefix = b"json:"
    except (TypeError, OverflowError, ValueError):
        if verbose:
            warnings.warn(
                "Object is not fully JSON-serialisable; hashing via pickle. "
                "The resulting digest may change across Python versions, "
                "platforms or build options.",
                UserWarning,
                stacklevel=2,
            )
        blob = pickle.dumps(obj, protocol=5, fix_imports=False)
        prefix = b"pickle:"

    return (prefix + hashlib.sha256(blob).hexdigest().encode()).decode()
