# Parameter Capability Matrix

This document records current probe methods and observed results for selected
OpenAI Responses API parameters when routed through this gateway to the Codex
backend.

Scope:

- Client surface: official OpenAI Python SDK through `base_url=http://127.0.0.1:8787/v1`.
- Gateway target: ChatGPT OAuth Codex backend path.
- Date of observations: 2026-05-02.
- Probe files: `examples/16_*` and later.

## Reasoning Effort And Summary

### Purpose

The `reasoning` parameter has two important subfields in the Codex-compatible
request shape:

- `reasoning.effort`: how much reasoning work the model should apply.
- `reasoning.summary`: whether the response should expose a public reasoning
  summary, and how detailed that summary should be.

The goal of this probe is to separate three questions:

1. What does `/codex/models` declare for the selected model?
2. Which `reasoning.effort` and `reasoning.summary` combinations are accepted
   by the backend?
3. Which accepted combinations return visible reasoning summary content in the
   response object?

### Probe Method

Probe file:

```text
examples/27_param_reasoning_effort_summary_matrix_probe.py
```

Run command:

```powershell
python examples/27_param_reasoning_effort_summary_matrix_probe.py
```

Method:

1. Read `/codex/models`.
2. Locate the selected `CODEX_GATEWAY_MODEL`.
3. Read `supported_reasoning_levels` from that model metadata.
4. Use those model-declared efforts as the `reasoning.effort` candidates.
5. Test each effort against these `reasoning.summary` values:

```text
auto
concise
detailed
```

6. Send the same deterministic Python-snippet prompt for every case.
7. Record:
   - request acceptance or rejection
   - upstream `actual_model`
   - response status
   - number of `reasoning` output items
   - number of visible reasoning summary items
   - total visible summary character count
   - final `output_text`

The probe intentionally does not treat final answer length as the semantic
effect of `reasoning.summary`. The visible reasoning summary inside
`response.output` is the relevant observation target.

### Model Metadata Observation

For `CODEX_GATEWAY_MODEL=gpt-5.2`, `/codex/models` returned:

```text
+-----------------+------------------+-----------------+---------------------------------+
| requested_model | supports_summary | default_summary | efforts                         |
+-----------------+------------------+-----------------+---------------------------------+
| gpt-5.2         | True             | auto            | ["low","medium","high","xhigh"] |
+-----------------+------------------+-----------------+---------------------------------+
```

### Matrix Result

The table below records the observed result from a real backend probe. The
caller requested `gpt-5.2`; the backend returned `gpt-5.4` as the actual model.

```text
+--------+----------+-----------------------------+--------------+-----------------+-----------------+---------------+---------------+-------------+
| effort | summary  | status                      | actual_model | response_status | reasoning_items | summary_items | summary_chars | output_text |
+--------+----------+-----------------------------+--------------+-----------------+-----------------+---------------+---------------+-------------+
| low    | auto     | supported_with_summary      | gpt-5.4      | completed       | 1               | 1             | 362           | 4           |
| low    | concise  | accepted_no_visible_summary | gpt-5.4      | completed       | 1               | 0             | 0             | 4           |
| low    | detailed | supported_with_summary      | gpt-5.4      | completed       | 1               | 1             | 409           | 4           |
| medium | auto     | supported_with_summary      | gpt-5.4      | completed       | 1               | 1             | 369           | 4           |
| medium | concise  | accepted_no_visible_summary | gpt-5.4      | completed       | 1               | 0             | 0             | 4           |
| medium | detailed | supported_with_summary      | gpt-5.4      | completed       | 1               | 1             | 397           | 4           |
| high   | auto     | supported_with_summary      | gpt-5.4      | completed       | 1               | 1             | 423           | 4           |
| high   | concise  | accepted_no_visible_summary | gpt-5.4      | completed       | 1               | 0             | 0             | 4           |
| high   | detailed | supported_with_summary      | gpt-5.4      | completed       | 1               | 1             | 452           | 4           |
| xhigh  | auto     | supported_with_summary      | gpt-5.4      | completed       | 1               | 1             | 431           | 4           |
| xhigh  | concise  | accepted_no_visible_summary | gpt-5.4      | completed       | 1               | 0             | 0             | 4           |
| xhigh  | detailed | supported_with_summary      | gpt-5.4      | completed       | 1               | 1             | 399           | 4           |
+--------+----------+-----------------------------+--------------+-----------------+-----------------+---------------+---------------+-------------+
```

### Current Conclusions

- `reasoning.effort=low|medium|high|xhigh` was accepted for the selected model.
- `reasoning.summary=auto|concise|detailed` was accepted.
- `summary=auto` returned visible reasoning summaries in this probe.
- `summary=detailed` returned visible reasoning summaries in this probe.
- `summary=concise` was accepted but did not return visible summary content in
  this probe.
- `summary=detailed` generally produced visible summaries similar to or longer
  than `summary=auto`, but the length is not guaranteed to be strictly
  monotonic.
- The final answer stayed stable as `output_text=4` across all cases, which is
  useful because it keeps the observation focused on the reasoning summary
  component.
- The backend returned `actual_model=gpt-5.4` even though the client requested
  `gpt-5.2`. This should be treated as upstream routing or upgrade behavior,
  not gateway-side model normalization.

### Gateway Implications

- The gateway should preserve caller-provided `reasoning.effort` and
  `reasoning.summary` values.
- The gateway may use `/codex/models` to discover supported effort levels for
  diagnostics and examples.
- The gateway should not invent a complete `summary` support list from
  `/codex/models`, because the model metadata currently declares
  `supports_reasoning_summaries` and `default_reasoning_summary`, but not a
  `supported_reasoning_summaries` list.
- If the caller omits `reasoning.summary`, the current gateway behavior of
  filling `summary="auto"` is a Codex compatibility choice and should remain
  documented.

## Text Verbosity

### Purpose

The `text.verbosity` parameter controls the expected detail level of the final
text answer. It should be observed through `output_text`, not through the
reasoning summary component.

This probe is designed to answer three questions:

1. Does `/codex/models` declare verbosity support for the selected model?
2. Does the backend accept `text.verbosity=low|medium|high`?
3. Does changing `text.verbosity` produce observable differences in output
   length or detail when all other important inputs are fixed?

### Probe Method

Probe file:

```text
examples/28_param_text_verbosity_probe.py
```

Run command:

```powershell
python examples/28_param_text_verbosity_probe.py
```

Method:

1. Read `/codex/models`.
2. Locate the selected `CODEX_GATEWAY_MODEL`.
3. Read `support_verbosity` and `default_verbosity` from that model metadata.
4. Keep the reasoning settings fixed:

```json
{"effort": "medium", "summary": "auto"}
```

5. Send the same explanatory Python-snippet prompt for every case.
6. Test these `text.verbosity` values:

```text
low
medium
high
```

7. Record:
   - request acceptance or rejection
   - requested model
   - observed upstream actual model
   - response status
   - output character count
   - output word count
   - output non-empty line count
   - complete `output_text`

The probe intentionally uses an explanation prompt rather than a fixed short
answer prompt, because verbosity needs room to affect the amount of final text.
The probe also prints the full output for each case, because length alone is
not a complete measure of answer detail.

### Expected Output Shape

`28_param_text_verbosity_probe.py` first prints model metadata and observed
actual models. The actual model is collected from real backend responses, not
inferred from `/codex/models`.

```text
+-----------------+------------------------+-------------------+-------------------+---------------------------+
| requested_model | observed_actual_models | support_verbosity | default_verbosity | tested_values             |
+-----------------+------------------------+-------------------+-------------------+---------------------------+
| gpt-5.2         | ["gpt-5.4"]            | True              | low               | ["low","medium","high"]   |
+-----------------+------------------------+-------------------+-------------------+---------------------------+
```

The probe then prints one row per tested verbosity value:

```text
+-----------+-----------+--------------+-----------------+-------+-------+-------+
| verbosity | status    | actual_model | response_status | chars | words | lines |
+-----------+-----------+--------------+-----------------+-------+-------+-------+
| low       | supported | ...          | completed       | ...   | ...   | ...   |
| medium    | supported | ...          | completed       | ...   | ...   | ...   |
| high      | supported | ...          | completed       | ...   | ...   | ...   |
+-----------+-----------+--------------+-----------------+-------+-------+-------+
```

### Interpretation Rules

- If all three requests complete, `text.verbosity=low|medium|high` should be
  recorded as accepted for the selected backend path.
- If output counts and full text differ across values, the probe provides
  evidence that verbosity has an observable effect.
- Do not require strict monotonicity such as `low < medium < high` for every
  run. Verbosity is a style/detail control, not a hard token budget.
- Keep `reasoning` fixed while probing verbosity so output differences are not
  conflated with reasoning effort or summary behavior.
- Treat `actual_model` as upstream routing or upgrade behavior when it differs
  from `requested_model`.

### Current Status

The probe has been implemented, but no project-level result matrix is recorded
yet. Run `examples/28_param_text_verbosity_probe.py` against a live gateway and
record the observed table here.

## Service Tier

### Purpose

The `service_tier` parameter controls the speed tier requested for a single
response-generation call. In this gateway, it should be handled as a transparent
request-body field:

- If the caller omits `service_tier`, the gateway should omit it too. The Codex
  backend then uses its default standard speed.
- If the caller sends a value, the gateway should forward that value unchanged
  and let the Codex backend accept or reject it.

`/codex/models` may expose fields such as `service_tiers` and
`additional_speed_tiers`, but those fields are capability or display metadata.
They should not be used to infer the current user speed setting, the current
request speed, or whether a previous request changed any state.

### Probe Method

Probe file:

```text
examples/29_param_service_tier_probe.py
```

Run command:

```powershell
python examples/29_param_service_tier_probe.py
```

Method:

1. Keep the reasoning and text settings fixed:

```json
{"reasoning":{"effort":"medium","summary":"auto"},"text":{"verbosity":"low"}}
```

2. Send the same exact-answer prompt for every case:

```text
Reply exactly: service-tier-probe-ok
```

3. Test these request-body cases:

```text
omitted
priority
auto
default
flex
fast
```

4. Record request acceptance, upstream `actual_model`, response status,
   response `service_tier`, elapsed milliseconds, final `output_text`, and the
   full backend error observation for rejected values.

The probe intentionally does not call `/codex/models` after each request,
because `/codex/models` is not a current-speed state API.

### Result Matrix

Last recorded real-backend observation:

```text
+----------+-------------------+----------+--------------+-----------------+-----------------------+-----------------------+-------------------------------------+
| case     | sent_service_tier | status   | actual_model | response_status | response_service_tier | output_text           | observation                         |
+----------+-------------------+----------+--------------+-----------------+-----------------------+-----------------------+-------------------------------------+
| omitted  | <absent>          | accepted | gpt-5.4      | completed       | default               | service-tier-probe-ok | request accepted                    |
| priority | priority          | accepted | gpt-5.4      | completed       | default               | service-tier-probe-ok | request accepted                    |
| auto     | auto              | rejected |              |                 |                       |                       | Unsupported service_tier: auto      |
| default  | default           | rejected |              |                 |                       |                       | Unsupported service_tier: default   |
| flex     | flex              | rejected |              |                 |                       |                       | Unsupported service_tier: flex      |
| fast     | fast              | rejected |              |                 |                       |                       | Unsupported service_tier: fast      |
+----------+-------------------+----------+--------------+-----------------+-----------------------+-----------------------+-------------------------------------+
```

### Interpretation

```text
+----------+----------------------------------------------------------------------+
| case     | interpretation                                                       |
+----------+----------------------------------------------------------------------+
| omitted  | Uses Codex backend default standard speed.                           |
| priority | Accepted backend wire value for fast/priority speed.                 |
| auto     | Official OpenAI value, but rejected by the current Codex backend path.|
| default  | Official OpenAI value, but rejected by the current Codex backend path.|
| flex     | Official OpenAI value, but rejected by the current Codex backend path.|
| fast     | Codex CLI/UI alias; not accepted as the backend wire value.           |
+----------+----------------------------------------------------------------------+
```

### Gateway Implications

- Do not infer `service_tier` from `/codex/models`.
- Do not fill `service_tier` when the caller omits it.
- Do not translate `fast` to `priority` inside the gateway; that would make the
  gateway a policy layer rather than a transparent proxy.
- Forward explicit caller values unchanged and preserve backend rejection
  behavior.
- Treat `response.service_tier=default` as backend response metadata. It should
  not be used to conclude that `/codex/models` or user settings changed.

## Metadata

### Purpose

The official Responses API `metadata` parameter lets callers attach custom
key-value labels to a Response object. These labels are intended for system
management, tracing, filtering, and observability. They are not instructions to
the model and should not affect model output.

Codex CLI source code currently exposes a private `client_metadata` field in
its `ResponsesApiRequest`, but it does not expose the official `metadata`
field. Therefore this probe tests a likely compatibility boundary between the
official OpenAI API shape and the Codex backend path.

### Probe Method

Probe file:

```text
examples/30_param_metadata_probe.py
```

Run command:

```powershell
python examples/30_param_metadata_probe.py
```

Method:

1. Send the same exact-answer prompt for every case:

```text
Reply exactly: metadata-probe-ok
```

2. Send one representative non-empty metadata object:

```json
{"probe":"metadata","scenario":"basic","trace_id":"metadata-probe-001"}
```

3. Record whether the request is rejected by the client, rejected by the
   gateway/backend path, accepted without echo, accepted with partial echo, or
   accepted with exact `response.metadata` echo.

### Result Matrix

Last recorded real-backend observation:

```text
+------------------+------------------+-----------------+-------------------+-------------------------------+
| case             | status           | response_status | response_metadata | observation                   |
+------------------+------------------+-----------------+-------------------+-------------------------------+
| basic            | backend_rejected |                 |                   | Unsupported parameter: metadata |
+------------------+------------------+-----------------+-------------------+-------------------------------+
```

### Test Intent

```text
+-------+----------------------------------------------------------+
| case  | intent                                                   |
+-------+----------------------------------------------------------+
| basic | Verify whether official metadata is accepted and echoed. |
+-------+----------------------------------------------------------+
```

### Current Conclusions

- The current Codex backend path rejects official `metadata` with
  `Unsupported parameter: metadata`.
- The OpenAI Python SDK allowed the tested `metadata` payloads to be sent to the
  gateway path; the observed failure came from the gateway/backend response.
- `metadata` should be documented as unsupported for the current Codex backend
  path.
- Do not map official `metadata` to Codex private `client_metadata` in the
  gateway. They are different protocol fields with different ownership and
  should not be conflated by a transparent proxy.

### Gateway Implications

- Keep transparent forwarding behavior for explicit caller-provided
  `metadata`.
- Preserve the backend rejection rather than silently dropping the field.
- If a future compatibility mode maps metadata into a gateway-specific header
  or private field, it should be explicit, opt-in, and documented separately
  from OpenAI API compatibility.
