# Artifact extraction admission v1

Status: **ADMITTED**

A sanitized cross-format contract-conformance pack derived from a frozen consumer boundary. It measures supported syntax exactly; it is not a representative estimate of extraction accuracy on arbitrary documents.

Receipt: `d29453cf75ea3da89204869fc12b7aeafb8bd8443f07e15e5707d9a6e0322058`
Benchmark: `96c3b4e34e22e376dedb6e347b7f9649432104c65ac3af4a59afa2c0b92fc625`
Profile: `host-artifact-admission` / `4ca376dd5faca7877d20020859c0058de53e2c1ac8b3f4d3bcb8051098709c20`

| Kind | Expected | Actual | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| `structured_json` | 4 | 4 | 1.000 | 1.000 | 1.000 |
| `rendered_html` | 9 | 9 | 1.000 | 1.000 | 1.000 |
| `markdown` | 7 | 7 | 1.000 | 1.000 | 1.000 |

Aggregate: precision `1.000`, recall `1.000`, F1 `1.000`, field accuracy `1.000`, location coverage `1.000`.

This admits the frozen syntax contract only. It does not establish representative accuracy on arbitrary reports.
