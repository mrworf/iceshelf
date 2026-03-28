# Glacier Provider

Stores backups in Amazon Glacier using boto3.

## Arguments
- `vault` – name of the Glacier vault.
- `threads` – optional number of upload threads (default 4).

## AWS Credentials

Credentials can be provided in the provider section or via a YAML config file:

```ini
[provider-glacier]
type: glacier
vault: myvault
region: us-east-1
access key id: AKIAIOSFODNN7EXAMPLE
secret access key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

Alternatively use a named profile:
```ini
profile: myprofile
```

Or point to a YAML config file:
```ini
aws config: /path/to/aws.yaml
```

The YAML file may contain: `region`, `access_key_id`, `secret_access_key`,
`session_token`, `profile`, `endpoint_url`.

## Pros
- Data is stored immutably which offers strong protection against ransomware.
- Very low storage cost for large archives.

## Cons
- Retrieval can take many hours and incurs additional cost.
