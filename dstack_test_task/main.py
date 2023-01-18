#!/usr/bin/env python3

import datetime
from abc import abstractmethod
from types import TracebackType
from typing import Iterator, Literal, Optional, Protocol, Type

import boto3
import click
import docker
from docker.client import DockerClient
from docker.models.containers import Container as DockerContainer
from mypy_boto3_logs.client import CloudWatchLogsClient
from mypy_boto3_logs.type_defs import InputLogEventTypeDef


class ILogProvider(Protocol):
    @abstractmethod
    def write(self, msg: str) -> None: ...

    @abstractmethod
    def __str__(self) -> str: ...


class CloudWatchProvider(ILogProvider):
    def __init__(self, client: CloudWatchLogsClient, group_name: str, stream_name: str) -> None:
        self._client = client
        self.group_name = group_name
        self.stream_name = stream_name

        self._create_log_group()
        self._create_log_stream()

    def _create_log_group(self) -> None:
        try:
            click.echo(f'Creating log group: "{self.group_name}"')
            self._client.create_log_group(logGroupName=self.group_name)
        except self._client.exceptions.ResourceAlreadyExistsException as err:
            click.echo(f"Log group already exists. Re-using")

    def _create_log_stream(self) -> None:
        try:
            click.echo(f'Creating log stream: "{self.stream_name}"')
            self._client.create_log_stream(logGroupName=self.group_name, logStreamName=self.stream_name)
        except self._client.exceptions.ResourceAlreadyExistsException as err:
            click.echo(f"Log stream already exists. Re-using\n")

    def write(self, msg: str) -> None:
        log: InputLogEventTypeDef = {"timestamp": int(datetime.datetime.utcnow().timestamp() * 1000), "message": msg}
        self._client.put_log_events(
            logGroupName=self.group_name,
            logStreamName=self.stream_name,
            logEvents=[log],
        )

    def __str__(self) -> str:
        return f"/{self.group_name}/{self.stream_name}"


class DockerLoggedExecutionContext:
    def __init__(self, container: DockerContainer, log_provider: ILogProvider) -> None:
        self.container = container
        self._log_provider = log_provider

    def _collect_logs(self) -> None:
        click.echo("Collecting logs to: " + str(self._log_provider) + "\n")

        logs: Iterator[bytes] = self.container.logs(stream=True)
        for log in logs:
            log_processed: str = log.decode('utf-8').strip()
            self._log_provider.write(log_processed)

    def __enter__(self) -> "DockerLoggedExecutionContext":
        return self

    def __exit__(
        self, 
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> Literal[True]:
        if exc_type == KeyboardInterrupt:
            click.echo('\nInterrupted! Gracefully stopping container.')
            click.echo('Press CTRL+C again to force quit. Data loss may occur!\n')

        self.container.stop()
        self._collect_logs()
        self.container.remove()
        return True


@click.command
@click.option("--docker-image", required=True, type=str, help="Name of docker image to use")
@click.option("--bash-command", required=True, type=str, help="Bash command will be executed in container")
@click.option("--aws-cloudwatch-group", required=True, type=str, help="Name of CloudWatch log group")
@click.option("--aws-cloudwatch-stream", required=True, type=str, help="Name of CloudWatch log stream under log group")
@click.option("--aws-access-key-id", required=True, type=str, help="AWS Access Key ID")
@click.option("--aws-secret-access-key", required=True, type=str, help="AWS Secret Access Key")
@click.option("--awsregion", required=True, type=str, help="AWS region name")
def cli(
    docker_image: str,
    bash_command: str,
    aws_cloudwatch_group: str,
    aws_cloudwatch_stream: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    awsregion: str,
) -> None:
    """CLI tool taht runs docker container with given command and outputs logs to AWS CloudWatch"""

    docker_client: DockerClient = docker.from_env()
    docker_container: DockerContainer = docker_client.containers.create(
        image=docker_image,
        command=["/bin/bash", "-c", f"eval $'{bash_command}'"],
        detach=False,
        environment={"PYTHONUNBUFFERED": 1}
    )
    logs_client: CloudWatchLogsClient = boto3.client(
        "logs",
        region_name=awsregion,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )
    cw_log_provider = CloudWatchProvider(logs_client, aws_cloudwatch_group, aws_cloudwatch_stream)

    with DockerLoggedExecutionContext(container=docker_container, log_provider=cw_log_provider) as ctx:
        click.echo('\nRunning docker container:')
        click.echo(f'\tImage: {ctx.container.image}')
        click.echo(f'\tName: {ctx.container.name}')
        click.echo(f'\tID: {ctx.container.id}')
        click.echo(f'\tCommand: {bash_command}\n')

        ctx.container.start()
        ctx.container.wait()


if __name__ == "__main__":
    cli()
