import click
import pendulum
from tabulate import tabulate

from prefect import config
from prefect.client import Client
from prefect.utilities.cli import open_in_playground
from prefect.utilities.graphql import with_args, EnumValue


@click.group(hidden=True)
def get():
    """
    Get commands that refer to querying Prefect Cloud metadata.
    """
    pass


# TODO: Age should not be created, due to scheduled runs, should be start time!
@get.command()
@click.option("--name", "-n", help="A flow name to query.")
@click.option("--version", "-v", type=int, help="A flow version to query.")
@click.option("--project", "-p", help="The name of a project to query.")
@click.option("--limit", "-l", default=10, help="A limit amount of tasks to query.")
@click.option("--all-versions", is_flag=True, help="Query all flow versions.")
@click.option("--playground", is_flag=True, help="Open this query in the playground.")
def flows(name, version, project, limit, all_versions, playground):
    """
    Query information regarding your Prefect flows.
    """

    distinct_on = EnumValue("name")
    if all_versions:
        distinct_on = None

    query = {
        "query": {
            with_args(
                "flow",
                {
                    "where": {
                        "_and": {
                            "name": {"_eq": name},
                            "version": {"_eq": version},
                            "project": {"name": {"_eq": project}},
                        }
                    },
                    "order_by": {
                        "name": EnumValue("asc"),
                        "version": EnumValue("desc"),
                    },
                    "distinct_on": distinct_on,
                    "limit": limit,
                },
            ): {
                "name": True,
                "version": True,
                "project": {"name": True},
                "created": True,
            }
        }
    }

    if playground:
        open_in_playground(query)
        return

    result = Client().graphql(query)

    flow_data = result.data.flow

    output = []
    for item in flow_data:
        output.append(
            [
                item.name,
                item.version,
                item.project.name,
                pendulum.parse(item.created).diff_for_humans(),
            ]
        )

    click.echo(
        tabulate(
            output,
            headers=["NAME", "VERSION", "PROJECT NAME", "AGE"],
            tablefmt="plain",
            numalign="left",
            stralign="left",
        )
    )


@get.command()
@click.option("--name", "-n", help="A project name to query.")
@click.option("--playground", is_flag=True, help="Open this query in the playground.")
def projects(name, playground):
    """
    Query information regarding your Prefect projects.
    """
    query = {
        "query": {
            with_args(
                "project",
                {
                    "where": {"_and": {"name": {"_eq": name}}},
                    "order_by": {"name": EnumValue("asc")},
                },
            ): {
                "name": True,
                "created": True,
                "description": True,
                with_args("flows_aggregate", {"distinct_on": EnumValue("name")}): {
                    EnumValue("aggregate"): EnumValue("count")
                },
            }
        }
    }

    if playground:
        open_in_playground(query)
        return

    result = Client().graphql(query)

    project_data = result.data.project

    output = []
    for item in project_data:
        output.append(
            [
                item.name,
                item.flows_aggregate.aggregate.count,
                pendulum.parse(item.created).diff_for_humans(),
                item.description,
            ]
        )

    click.echo(
        tabulate(
            output,
            headers=["NAME", "FLOW COUNT", "AGE", "DESCRIPTION"],
            tablefmt="plain",
            numalign="left",
            stralign="left",
        )
    )


@get.command()
@click.option("--limit", "-l", default=10, help="A limit amount of flow runs to query.")
@click.option("--flow", "-f", help="Specify a flow's runs to query.")
@click.option("--project", "-p", help="Specify a project's runs to query.")
@click.option("--playground", is_flag=True, help="Open this query in the playground.")
def flow_runs(limit, flow, project, playground):
    """
    Query information regarding Prefect flow runs.
    """
    query = {
        "query": {
            with_args(
                "flow_run",
                {
                    "where": {
                        "_and": {
                            "flow": {
                                "_and": {
                                    "name": {"_eq": flow},
                                    "project": {"name": {"_eq": project}},
                                }
                            }
                        }
                    },
                    "limit": limit,
                    "order_by": {"created": EnumValue("desc")},
                },
            ): {
                "flow": {"name": True},
                "created": True,
                "state": True,
                "name": True,
                "duration": True,
            }
        }
    }

    if playground:
        open_in_playground(query)
        return

    result = Client().graphql(query)

    flow_run_data = result.data.flow_run

    output = []
    for item in flow_run_data:
        output.append(
            [
                item.name,
                item.state,
                pendulum.parse(item.created).diff_for_humans(),
                item.duration,
                item.flow.name,
            ]
        )

    click.echo(
        tabulate(
            output,
            headers=["NAME", "STATE", "AGE", "DURATION", "FLOW NAME"],
            tablefmt="plain",
            numalign="left",
            stralign="left",
        )
    )


@get.command()
@click.option("--name", "-n", help="A task name to query")
@click.option("--flow-name", "-fn", help="A flow name to query")
@click.option("--flow-version", "-fv", type=int, help="A flow version to query.")
@click.option("--project", "-p", help="The name of a project to query.")
@click.option("--limit", "-l", default=10, help="A limit amount of tasks to query.")
@click.option("--playground", is_flag=True, help="Open this query in the playground.")
def tasks(name, flow_name, flow_version, project, limit, playground):
    """
    Query information regarding your Prefect tasks.
    """

    query = {
        "query": {
            with_args(
                "task",
                {
                    "where": {
                        "_and": {
                            "name": {"_eq": name},
                            "flow": {
                                "name": {"_eq": flow_name},
                                "project": {"name": {"_eq": project}},
                                "version": {"_eq": flow_version},
                            },
                        }
                    },
                    "limit": limit,
                    "order_by": {"created": EnumValue("desc")},
                },
            ): {"name": True, "created": True, "flow": {"name": True}, "type": True}
        }
    }

    if playground:
        open_in_playground(query)
        return

    result = Client().graphql(query)

    task_data = result.data.task

    output = []
    for item in task_data:
        output.append(
            [
                item.name,
                pendulum.parse(item.created).diff_for_humans(),
                item.flow.name,
                item.type,
            ]
        )

    click.echo(
        tabulate(
            output,
            headers=["NAME", "AGE", "FLOW NAME", "TYPE"],
            tablefmt="plain",
            numalign="left",
            stralign="left",
        )
    )