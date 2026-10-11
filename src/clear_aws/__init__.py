"""CLEAR on AWS (docs/PLAN.md §2c, §4c, §5b, §8d).

Adapters that run the same tool logic and agents on AgentCore and DynamoDB:

- dynamo_store: the data store on DynamoDB, with the interface of JsonStore.
- lambda_tools: the Lambda function behind AgentCore Gateway that runs the tools.
- gateway: the agents' tools as calls through AgentCore Gateway.
- runtime: what the AgentCore Runtime entrypoint does with an invocation.
- remote: the UI side, which starts runs on AgentCore Runtime.
- agentcore: the AgentCore CLI project configuration (agentcore.json).

Nothing here is needed to run CLEAR locally, and the tests use stand-ins for
every AWS call (docs/deployment.md).
"""
