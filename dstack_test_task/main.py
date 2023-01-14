#!/usr/bin/env python3

import datetime
from abc import abstractmethod
from typing import Any, List, Optional, Protocol

import boto3
import click
import docker
from mypy_boto3_logs.client import CloudWatchLogsClient
from mypy_boto3_logs.type_defs import InputLogEventTypeDef


class ILogProvider(Protocol):
    @abstractmethod
    def init(self) -> None: ...

    @abstractmethod
    def write(self, msg: str) -> None: ...


class CloudWatchProvider(ILogProvider):
    def __init__(self, client: CloudWatchLogsClient, group_name: str, stream_name: str) -> None:
        self._client = client
        self.group_name = group_name
        self.stream_name = stream_name

    def _create_log_group(self) -> None:
        try:
            click.echo(f'Creating log group: "{self.group_name}"')
            self._client.create_log_group(logGroupName=self.group_name)
        except self._client.exceptions.ResourceAlreadyExistsException as err:
            click.echo(f'Log group already exists. Re-using')

    def _create_log_stream(self) -> None:
        try:
            click.echo(f'Creating log stream: "{self.stream_name}"')
            self._client.create_log_stream(logGroupName=self.group_name, logStreamName=self.stream_name)
        except self._client.exceptions.ResourceAlreadyExistsException as err:
            click.echo(f'Log stream already exists. Re-using\n')

    def init(self) -> None:
        self._create_log_group()
        self._create_log_stream()

    def write(self, msg: str) -> None:
        log: InputLogEventTypeDef = {"timestamp": int(datetime.datetime.utcnow().timestamp() * 1000), "message": msg}
        click.echo(log)
        self._client.put_log_events(
            logGroupName=self.group_name,
            logStreamName=self.stream_name,
            logEvents=[log],
        )


class DockerContainer:
    def __init__(self, client, image: str, cmd: str) -> None:
        self._client = client
        self._container: Optional[Any] = None

        self.image = image
        self.cmd = self._format_cmd(cmd)

    def _format_cmd(self, cmd: str) -> List[str]:
        return ["sh", "-c", cmd]

    def _run(self):
        container = self._client.containers.run(
            image=self.image,
            command=self.cmd,
            stdout=True,
            stderr=True,
            detach=True
        )
        return container

    def __enter__(self):
        self._container = self._run()

        click.echo('\nRunning container:')
        click.echo(f'\tImage: {self.image}')
        click.echo(f'\tContainer name: {self._container.name}')
        click.echo(f'\tContainer ID: {self._container.id}')
        click.echo(f'\tCommand: {self.cmd}\n')
        return self._container

    def __exit__(self, exc_type: BaseException, exc_value, traceback):
        if exc_type == KeyboardInterrupt:
            click.echo('Interrupted! Gracfully destroying container.')
            click.echo('Press CTRL+C again to force quit.')

        self._container.stop()
        self._container.remove()


@click.command
@click.option("--docker-image", required=True, type=str, help='Name of docker image to use')
@click.option("--bash-command", required=True, type=str, help='Bash command will be executed in container')
@click.option("--aws-cloudwatch-group", required=True, type=str, help='Name of CloudWatch log group')
@click.option("--aws-cloudwatch-stream", required=True, type=str, help='Name of CloudWatch log stream under log group')
@click.option("--aws-access-key-id", required=True, type=str, help='AWS Access Key ID')
@click.option("--aws-secret-access-key", required=True, type=str, help='AWS Secret Access Key')
@click.option("--awsregion", required=True, type=str, help='AWS region name')
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

    docker_client = docker.from_env()
    logs_client: CloudWatchLogsClient = boto3.client(
        "logs",
        region_name=awsregion,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )

    with DockerContainer(docker_client, docker_image, bash_command) as container:
        cwp = CloudWatchProvider(logs_client, aws_cloudwatch_group, aws_cloudwatch_stream)
        cwp.init()
        for log_line in container.logs(stream=True, follow=True):
            cwp.write(log_line.decode('utf-8').strip())


if __name__ == "__main__":
    cli()
