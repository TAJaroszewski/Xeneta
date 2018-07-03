# TAJaroszewski
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, MetaData, Column, String, Date, Integer
from flask import Flask, jsonify, request, abort as flask_abort
from re import match, compile
from flask_caching import Cache
from json_encoder import CustomJSONEncoder
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('xeneta-api-chalange')

Base = declarative_base()


class PricesDB(Base):
    __tablename__ = "prices"
    orig_code = Column('orig_code', String(32), primary_key=True)
    dest_code = Column('dest_code', String(32))
    day = Column('day', Date)
    price = Column('price', Integer)


# APP Config and Initialization
app = Flask('Xeneta-API-Challenge')

app.config['HTTP_HOST'] = '0.0.0.0'
app.config['HTTP_PORT'] = 8080
app.config['DEBUG'] = True
app.config["JSON_SORT_KEYS"] = False
app.config['PORT_REGEXP'] = r'\b[A-Z]{5}\b'
# or isoformat()
app.config['DATE_FORMAT'] = "%Y-%m-%d"

# Cache Config and Initialization
# https://pythonhosted.org/Flask-Caching/#built-in-cache-backends
app.config['CACHE_TYPE'] = 'spreadsaslmemcached'
# Timeout: 300[s] = 5[m]
app.config['CACHE_DEFAULT_TIMEOUT'] = 3000
app.config['CACHE_KEY_PREFIX'] = 'xeneta_'
# ToDo: Memcache service discovery via Consul or direct ARN (AWS)
app.config['CACHE_MEMCACHED_SERVERS'] = ['127.0.0.1:11211']
app.config['CACHE_MEMCACHED_USERNAME'] = None
app.config['CACHE_MEMCACHED_PASSWORD'] = None

app.cache = Cache(app)

# DB Config and Initialization
POSTGRES = {
    'user': 'postgres',
    'pw': '',
    'db': 'postgres',
    'host': 'localhost',
    'port': '5432',
}

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://%(user)s:%(pw)s@%(host)s:%(port)s/%(db)s' % POSTGRES

app.cache.init_app(app)

db = SQLAlchemy()

###
app.json_encoder = CustomJSONEncoder
db.init_app(app)

engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'], echo=True)
metadata = MetaData(bind=engine)
Session = scoped_session(sessionmaker(bind=engine))
s = Session()


def query_db(sql):
    try:
        cursor = s.execute(sql)
        output = []
        for row in cursor:
            output.append(dict(row))
    except Exception as e:
        return jsonify({'message': 'Task failed: {}'.format(e)}), 500

    return output


def delta_days(date_from, date_to):
    date_format = app.config['DATE_FORMAT']
    return (datetime.strptime(date_to, date_format) - datetime.strptime(date_from, date_format)).days


def list_delta_days(date_from, date_to):
    delta_days_list = []
    date_format = app.config['DATE_FORMAT']
    days = int(
        (datetime.strptime(date_to, date_format) - datetime.strptime(date_from, date_format)) / timedelta(days=1))
    dt_obj = datetime.strptime(date_from, date_format)
    for i in range(0, days):
        delta_days_list.append(dt_obj + timedelta(days=i))
        logging.info(dt_obj + timedelta(days=i))
    logging.info(delta_days_list)
    return delta_days_list


def check_request_string(string):
    r = compile("^[a-zA-Z0-9\-_]+$")
    if r.match(string) is None:
        flask_abort('Issue with requests')


def check_request_number(number):
    r = compile("^[0-9]+$")
    if r.match(number) is None:
        flask_abort('Issue with requests')


@app.cache.memoize(timeout=app.config['CACHE_DEFAULT_TIMEOUT'])
def show_price_ranges(date_from, date_to, origin, destination):
    if match(app.config['PORT_REGEXP'], origin):
        port_origin = '\'{0}\''.format(origin)
    else:
        origin_sql = """select code from ports where parent_slug IN (select slug from regions where parent_slug = '{}') OR parent_slug = '{}'""".format(
            origin, origin)
        logging.debug(origin_sql)
        try:
            port_origin_list = query_db(origin_sql)
        except Exception as e:
            return jsonify({'message': 'Task failed: {}'.format(e)}), 500

        port_origin = ', '.join('\'{0}\''.format(pd['code']) for pd in port_origin_list)

        if not port_origin:
            flask_abort('Issue with requests')

    if match(app.config['PORT_REGEXP'], destination):
        port_destination = '\'{0}\''.format(destination)
    else:
        port_destination_sql = """select code from ports where parent_slug IN (select slug from regions where parent_slug = '{}') OR parent_slug = '{}'""".format(
            destination, destination)
        logging.debug(port_destination_sql)
        try:
            port_destination_list = query_db(port_destination_sql)
        except Exception as e:
            return jsonify({'message': 'Task failed: {}'.format(e)}), 500

        port_destination = ', '.join('\'{0}\''.format(pd['code']) for pd in port_destination_list)

        if not port_destination:
            flask_abort('Issue with requests')

    logging.debug("PORT Origin: {}".format(port_origin))
    logging.debug("PORT Destination: {}".format(port_destination))

    prices_sql = """select day, round(avg(price), 2) as average_price from prices where day between '{}' AND '{}' AND orig_code IN ({}) AND dest_code IN ({}) group by day;""".format(
        date_from, date_to, port_origin, port_destination)
    logging.info(prices_sql)
    try:
        prices = query_db(prices_sql)
    except Exception as e:
        return jsonify({'message': 'Task failed: {}'.format(e)}), 500

    return prices


def submitPrices(date_from, date_to, origin, destination, price):
    date_ranges = list_delta_days(date_from, date_to)
    try:
        for day in range(0, len(date_ranges)):
            s.add_all([
                PricesDB(orig_code=origin, dest_code=destination, day=date_ranges[day], price=price)
            ])
        # Raw SQL.. yuukkk
        # insert_sql = """INSERT INTO prices (orig_code, dest_code, day, price) VALUES ('{}', '{}', '{}', '{}')""".format(
        #    origin, destination, date_from, price)
        s.commit()
        # Clean cache after each price change; Needs to be changed
        app.cache.clear()
    except Exception:  # replace with a more meaningful exception
        s.rollback()
        return "{'message': Insert failed'}"

    return "{'message': Insert succeed'}"


def jsonity(text):
    jsonitied_out = []
    try:
        for entry in range(len(text)):
            jsonitied_out.append(text[entry])
    except Exception as e:
        return jsonify({'message': 'Task failed: {}'.format(e)}), 500

    return jsonify(jsonitied_out)


@app.route("/rates", methods=['GET', 'POST'])
@app.cache.cached(timeout=app.config['CACHE_DEFAULT_TIMEOUT'], query_string=True)
def main():
    if request.method == 'GET':
        try:
            date_from = request.args.get('date_from')
            logging.info(date_from)
            check_request_string(date_from)

            date_to = request.args.get('date_to')
            logging.info(date_to)
            check_request_string(date_to)

            origin = request.args.get('origin')
            logging.info(origin)
            check_request_string(origin)

            destination = request.args.get('destination')
            logging.info(destination)
            check_request_string(destination)

            prices = show_price_ranges(date_from, date_to, origin, destination)

        except Exception as e:
            return jsonify({'message': 'Task failed: {}'.format(e)}), 500

        return jsonity(prices)

    elif request.method == 'POST':
        try:
            date_from = request.form['date_from']
            logging.info(date_from)
            check_request_string(date_from)

            date_to = request.form['date_to']
            logging.info(date_to)
            check_request_string(date_to)

            origin = request.form['origin_code']
            logging.info(origin)
            check_request_string(origin)

            destination = request.form['destination_code']
            logging.info(destination)
            check_request_string(destination)

            price = request.form['price']
            logging.info(price)
            check_request_number(price)

            prices = submitPrices(date_from, date_to, origin, destination, price)

        except Exception as e:
            return jsonify({'message': 'Task failed: {}'.format(e)}), 500

        return jsonify(prices)
    else:
        flask_abort('Unknown method')


if __name__ == '__main__':
    app.run(port=app.config['HTTP_PORT'], debug=app.config['DEBUG'], host=app.config['HTTP_HOST'])
