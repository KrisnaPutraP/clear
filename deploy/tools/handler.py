"""AWS Lambda entrypoint for the CLEAR tools behind AgentCore Gateway (docs/deployment.md).

scripts/build_deploy.py copies this file next to the clear_tools and
clear_aws packages into the function's code location. The work happens in
clear_aws.lambda_tools.
"""

from clear_aws.lambda_tools import lambda_handler  # noqa: F401
