# Model invocation

Laymbda accepts the same `state` and `questions` inputs as
`laya.Agent.predict`. The Lambda event is the request itself:

```json
{
  "state": "The content to evaluate",
  "questions": {
    "question_id": {
      "type": "noul",
      "instructions": "Is this statement true?"
    }
  }
}
```

Do not wrap the request in an API Gateway `body` property or encode it as a
JSON string.

## Request fields

| Field | Accepted value |
| --- | --- |
| `state` | A JSON string, object, or array |
| `questions` | A non-empty object keyed by your question IDs |

Question IDs are chosen by the caller and appear under the same keys in the
response. Each question requires a `type` and `instructions` value. The
runtime accepts any JSON value for `instructions`, though the examples use
plain strings.

## Token limits

The bundled English checkpoint has a 512-token context for each question.
Question instructions and criteria can consume up to roughly 192 tokens,
leaving about 320 tokens for the state. Shorter questions leave more room for
the state.

Laya keeps the beginning of a state that exceeds the available context and
truncates the remainder. Choice and score criteria share the question budget,
so large or verbose criteria sets leave less room for the state and may be
shortened. An invocation fails if Laya cannot represent every option within
the configured token budget.

## Choice questions

A `choice` question selects one named alternative. Its `criteria` can be a
non-empty array of labels:

```json
{
  "sentiment": {
    "type": "choice",
    "instructions": "What is the overall sentiment?",
    "criteria": ["negative", "neutral", "positive"]
  }
}
```

Use an object when each label needs a description:

```json
{
  "department": {
    "type": "choice",
    "instructions": "Which department should handle this request?",
    "criteria": {
      "billing": "invoices, payments, and refunds",
      "technical": "bugs, outages, and system errors",
      "sales": "pricing and new contracts"
    }
  }
}
```

## Score questions

A `score` question places the state on an ordered scale. The position of each
criterion determines its numeric index.

```json
{
  "urgency": {
    "type": "score",
    "instructions": "How urgent is this request?",
    "criteria": [
      "not urgent",
      "needs attention soon",
      "critical deadline or blocking issue"
    ]
  }
}
```

The criteria array must contain at least one item.

## Noul questions

A `noul` question returns the probability that its instruction is true:

```json
{
  "churn_risk": {
    "type": "noul",
    "instructions": "Does the user threaten to cancel or leave?"
  }
}
```

The optional `criteria` object can provide custom values for the `false` and
`true` outcomes:

```json
{
  "churn_risk": {
    "type": "noul",
    "instructions": "Does the user threaten to cancel or leave?",
    "criteria": {
      "false": "the user intends to stay",
      "true": "the user threatens to leave"
    }
  }
}
```

When supplied, `criteria` may contain only the `false` and `true` keys.

## Complete example

[`examples/support-ticket.json`](../examples/support-ticket.json) evaluates a
support request with one question of each type.

```json
{
  "state": {
    "from": "user@acme.com",
    "subject": "Duplicate charge on invoice #4411",
    "body": "We were billed twice for March. Please refund the duplicate today or we will cancel our plan."
  },
  "questions": {
    "department": {
      "type": "choice",
      "instructions": "Which department should handle this email?",
      "criteria": {
        "billing": "invoices, payments, and refunds",
        "technical": "bugs, outages, and system errors",
        "sales": "pricing and new contracts",
        "other": "anything outside the other categories"
      }
    },
    "urgency": {
      "type": "score",
      "instructions": "How urgent is this request?",
      "criteria": [
        "not urgent",
        "needs attention soon",
        "critical deadline or blocking issue"
      ]
    },
    "churn_risk": {
      "type": "noul",
      "instructions": "Does the user threaten to cancel or leave?"
    }
  }
}
```

## Response

The function returns Laya's native result and adds the Lambda request ID under
`metadata`. The included example produces this response shape:

```json
{
  "model": "laya-rl-agent",
  "answers": {
    "department": {
      "type": "choice",
      "choice": "billing",
      "probabilities": {
        "billing": 0.9569,
        "technical": 0.0173,
        "sales": 0.0132,
        "other": 0.0126
      },
      "confidence": 0.8381,
      "action": {
        "act_probability": 1.0
      }
    },
    "urgency": {
      "type": "score",
      "score": 1.2834,
      "legend": {
        "0": "not urgent",
        "1": "needs attention soon",
        "2": "critical deadline or blocking issue"
      },
      "probabilities": {
        "0": 0.0738,
        "1": 0.569,
        "2": 0.3572
      },
      "confidence": 0.1981,
      "action": {
        "act_probability": 1.0
      }
    },
    "churn_risk": {
      "type": "noul",
      "noul": 0.8158,
      "confidence": 0.8158,
      "action": {
        "act_probability": 1.0
      }
    }
  },
  "usage": {
    "input_tokens": 265,
    "output_tokens": 0
  },
  "metadata": {
    "request_id": "3d4e5932-26bd-4d8e-9b1f-5e205bb928a0"
  }
}
```

Scores, probabilities, confidence values, and token usage depend on the
request and model revision. `metadata.request_id` identifies the Lambda
invocation.

## Validation

The runtime validates every event before inference. It rejects:

- missing `state` or `questions` fields;
- an empty `questions` object;
- unsupported question types;
- missing or empty criteria where criteria are required;
- fields outside the documented request shape.

Validation errors identify the invalid field without including the supplied
state or field values in logs.

## AWS CLI

Invoke the deployed `live` alias with any request file:

```bash
aws lambda invoke \
  --function-name "$(aws cloudformation describe-stacks \
    --stack-name LaymbdaStack \
    --query "Stacks[0].Outputs[?OutputKey=='LiveAliasArn'].OutputValue" \
    --output text)" \
  --cli-binary-format raw-in-base64-out \
  --payload fileb://examples/support-ticket.json \
  response.json

cat response.json
```
