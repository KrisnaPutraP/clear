"""AgentCore Runtime entrypoint for CLEAR (docs/deployment.md).

scripts/build_deploy.py copies this file next to the clear_* packages into
the runtime's code location. The work happens in clear_aws.runtime.
"""

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from clear_aws import runtime

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload):
    return runtime.handle(payload)


if __name__ == "__main__":
    app.run()
