from diskcache import Cache

cache = Cache('../cache_dir')

class SavePoints:

    @staticmethod
    def save_layer_progress(cache_key, is_layer_cached):
        cache.set(cache_key, is_layer_cached)


    @staticmethod
    def get_layer_progress(cache_key):
        return cache.get(cache_key)


    @staticmethod
    def clear_all_progress(is_clear_cache=False):
        if is_clear_cache:
            cache.clear()
