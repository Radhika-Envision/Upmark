import collections
import datetime
from functools import lru_cache, wraps


class CacheEntry:
    def __init__(self, ob, t):
        self.ob = ob
        self.t = t


class LruCache(collections.OrderedDict):
    def __init__(self, items=tuple(), size=150, max_age=None):
        self.size = size
        if max_age is not None:
            self.max_age = max_age
        else:
            self.max_age = datetime.timedelta(days=1)
        super().__init__(items)

    def __getitem__(self, k):
        item = super().__getitem__(k)
        t = datetime.datetime.utcnow()
        if t - item.t > self.max_age:
            del self[k]
            raise KeyError
        item.t = datetime.datetime.utcnow()
        self.move_to_end(k)
        return item.ob

    def __setitem__(self, k, ob):
        item = CacheEntry(ob, datetime.datetime.utcnow())
        super().__setitem__(k, item)
        self.move_to_end(k)
        if len(self) > self.size:
            self.popitem(last=False)

    def __contains__(self, k):
        try:
            item = super().__getitem__(k)
        except KeyError:
            return False
        t = datetime.datetime.utcnow()
        if t - item.t > self.max_age:
            del self[k]
            return False
        return True


def instance_method_lru_cache(*cache_args, **cache_kwargs):
    '''
    Just like functools.lru_cache, but a new cache is created for each instance
    of the class that owns the method this is applied to.
    '''
    def cache_decorator(func):
        @wraps(func)
        def cache_factory(self, *args, **kwargs):
            # Wrap the function in a cache by calling the decorator
            instance_cache = lru_cache(*cache_args, **cache_kwargs)(func)
            # Bind the decorated function to the instance to make it a method
            instance_cache = instance_cache.__get__(self, self.__class__)
            setattr(self, func.__name__, instance_cache)
            # Call the instance cache now. Next time the method is called, the
            # call will go directly to the instance cache and not via this
            # decorator.
            return instance_cache(*args, **kwargs)
        return cache_factory
    return cache_decorator
