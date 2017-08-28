from clustermgr.application import create_app, init_celery
from clustermgr.extensions import celery

app = create_app()
init_celery(app, celery)


def main():
    app.run(debug=True)


if __name__ == "__main__":
    main()
