import pylibmc

# Experiment with memcache performance
def pylibmccache(app, config, args, kwargs):
    return pylibmc.Client(servers=config['CACHE_MEMCACHED_SERVERS'],
                          username=config['CACHE_MEMCACHED_USERNAME'],
                          password=config['CACHE_MEMCACHED_PASSWORD'],
                          binary=True,
                          behaviors={"tcp_nodelay": True})
