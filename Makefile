.PHONY: all

lint:
	flake8 . tests --ignore=E501

test:
	py.test -x tests/

clean:
	clean-build clean-pyc

clean-build:
	rm -rf build/ dist/

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +

docker-xeneta:
	docker build -t ratestask ratestask;
	docker run -p 0.0.0.0:5432:5432 --name ratestask ratestask;
	psql -h 127.0.0.1 -U postgres;

memcache:
	docker-memcache
	memcache_install
	stats_items
	
# https://hub.docker.com/_/memcached/
docker-memcache:
	docker pull memcached
	docker run -p 0.0.0.0:11211:11211 --name rate-memcache -d memcached

memcache_install:
	brew install libmemcached

test_items:
	time curl 'http://127.0.0.1:8080/rates?date_from=2016-01-01&date_to=2016-01-10&origin=CNSGH&destination=poland_main'

stats_items:
	(echo "stats items"; sleep 1) | telnet localhost 11211 2>/dev/null

tcpdump_items:
	sudo tcpdump -i lo0 -A port 11211

docker-redis:
	docker pull redis
	docker run -p 0.0.0.0:6379:6379 --name rate-redis -d redis

curl_tests:
	time curl 'http://127.0.0.1:8080/rates?date_from=2016-01-01&date_to=2016-01-31&origin=CNXAM&destination=baltic'
	time curl 'http://127.0.0.1:8080/rates?date_from=2016-01-01&date_to=2016-01-31&origin=CNXAM&destination=NOTRD'
	time curl 'http://127.0.0.1:8080/rates?date_from=2016-01-01&date_to=2016-01-31&origin=china_east_main&destination=north_europe_main'
