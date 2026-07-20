"""
cache_util.py
-------------
Clears the GeoServer project cache after ETL runs.

Usage from notebook:
    from cache_util import clear_cache

    clear_cache()                  # clear all projects
    clear_cache('akwaaba')         # clear one project
    clear_cache(['akwaaba', 'buffalo', 'colobus'])  # clear multiple
"""

import requests

BASE_URL = "https://geoserver2.rainforestbuilder.com/api/admin/cache/clear"


def clear_cache(project=None, timeout=30):
    """
    Clears the GeoServer cache.

    Parameters
    ----------
    project : str | list[str] | None
        Project name(s) to clear. Pass None to clear all caches.
    timeout : int
        Request timeout in seconds.
    """
    if project is None:
        _post_clear(timeout=timeout)

    elif isinstance(project, list):
        for p in project:
            _post_clear(project=p, timeout=timeout)

    else:
        _post_clear(project=project, timeout=timeout)


def _post_clear(project=None, timeout=30):
    url = BASE_URL if project is None else f"{BASE_URL}?project={project}"
    label = project if project else "all projects"
    try:
        response = requests.post(url, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        keys = result.get("keys_deleted", "?")
        print(f"Cache cleared [{label}]: {keys} keys deleted")
    except requests.exceptions.RequestException as e:
        print(f"Cache clear failed [{label}]: {e}")
