"""Startup invariants for marznode."""


class MissingAuthAlgorithm(RuntimeError):
    pass


def require_auth_algorithm_set(env) -> str:
    """AUTH_GENERATION_ALGORITHM must be set explicitly and equal to the
    panel's (almost always `plain`). marznode's config defaults it to
    xxh128 when unset, which derives a different UUID -> xray
    'invalid request user id', every client rejected while the node looks
    healthy. Refuse to start when unset; return the resolved value to log."""
    val = env.get("AUTH_GENERATION_ALGORITHM")
    if val is None or val.strip() == "":
        raise MissingAuthAlgorithm(
            "REFUSING TO START: AUTH_GENERATION_ALGORITHM is not set. "
            "marznode defaults to xxh128, which mismatches a panel using "
            "`plain` and rejects every client silently. Set it explicitly "
            "(must equal the panel's value, almost always `plain`)."
        )
    return val.strip()
