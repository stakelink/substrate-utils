from cachetools import TTLCache, Cache
from datetime import datetime

import cachetools
import time
import pickle

def hashkey(*args, **kwargs):
    new_args = []
    for i in range(0, len(args)):
       new_args.append(str(args[i]))
    args = tuple(new_args)

    for k in kwargs:
        kwargs[k] = str(kwargs[k])

    return(cachetools.keys.hashkey(*args, **kwargs))


class TTLCacheStorage(TTLCache):
    def __init__(self, maxsize, ttl, storage=None, storage_sync_timer=0, storage_load=True, timer=time.monotonic, getsizeof=None):
        self.storage = storage
        self.storage_sync_timer = storage_sync_timer

        now = datetime.timestamp(datetime.now())
        self.storage_sync_timer_next = now

        super().__init__(maxsize, ttl, timer, getsizeof)

        if self.storage is not None and storage_load:
            try:
                with open(self.storage, 'rb') as fh:
                    self._Cache__data = pickle.load(fh)
                    print("[TTLCacheStorage] Load", self.storage)
            except:
                pass

    def __getitem__(self, key, cache_getitem=TTLCache.__getitem__):
        v = cache_getitem(self, key)

        if self.storage is not None:
            now = datetime.timestamp(datetime.now())
            if self.storage_sync_timer_next <= now:
                self.storage_sync_timer_next = now + self.storage_sync_timer

                with open(self.storage, 'wb') as fh:
                    pickle.dump(self._Cache__data, fh)
                    print("[TTLCacheStorage] Sync", self.storage)

        return v

    def clear(self):
        print("[TTLCacheStorage] Clear")

        if self.storage is not None:
            with open(self.storage, 'wb') as fh:
                fh.truncate()

        self.__init__(
            self.maxsize,
            self.ttl,
            self.storage,
            self.storage_sync_timer,
            False,
            self.timer,
            self.getsizeof
        ) 
        None