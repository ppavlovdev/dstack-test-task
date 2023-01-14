# dstack.ai test task

## Description
CLI tool taht runs docker container with given command and outputs logs to AWS CloudWatch

## Requirements
- Python `>=3.8`
- Poetry `^1.3.2`

## Installation and usage
### Using poetry
```bash
$ pip install poetry
$ poetry install

# Run cli
$ poetry run dstack-cli --help
```

### Using setuptools
```bash
$ pip install poetry
$ poetry install --with dev

$ pip install -e .

# Run cli
$ dstack-cli --help
```

## Help
```bash
$ dstack-cli --help

Usage: dstack-cli [OPTIONS]

  CLI for running docker container with log output to AWS ClodWatch

Options:
  --docker-image TEXT           Name of docker image to use  [required]
  --bash-command TEXT           Bash command will be executed in container
                                [required]
  --aws-cloudwatch-group TEXT   Name of CloudWatch log group  [required]
  --aws-cloudwatch-stream TEXT  Name of CloudWatch log stream under log group
                                [required]
  --aws-access-key-id TEXT      AWS Access Key ID  [required]
  --aws-secret-access-key TEXT  AWS Secret Access Key  [required]
  --awsregion TEXT              AWS region name  [required]
  --help                        Show this message and exit.
```