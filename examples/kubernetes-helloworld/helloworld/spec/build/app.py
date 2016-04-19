import os
from flask import Flask
from redis import Redis

redisHost=os.environ['REDIS_MASTER_SERVICE_HOST']
redisPort=os.environ['REDIS_MASTER_SERVICE_PORT']

app = Flask(__name__)
redis = Redis(host=redisHost, port=redisPort)

@app.route('/')
def hello():
    redis.incr('hits')
    return 'Hello World! I have been seen %s times.' % redis.get('hits')

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
