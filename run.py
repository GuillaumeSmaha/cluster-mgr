from clustermgr.application import create_app, init_celery
from clustermgr.extensions import celery

app = create_app()
init_celery(app, celery)


if __name__ == "__main__":
    app.run(debug=True)
