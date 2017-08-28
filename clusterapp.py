import click

from clustermgr.application import create_app, init_celery
from clustermgr.extensions import celery
from flask.cli import FlaskGroup

app = create_app()
init_celery(app, celery)


def create_cluster_app(info):
    return create_app()


@click.group(cls=FlaskGroup, create_app=create_cluster_app)
def cli():
    """This is a management script for the wiki application"""
    pass


if __name__ == "__main__":
    cli()
