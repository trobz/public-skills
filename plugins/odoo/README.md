# Odoo Plugin

Odoo data inspection, querying, and access-rights comparison toolkit using the `odooly` CLI.

## Requirements

- `odooly` available in `$PATH`
- Configuration file at `~/odooly.ini`

## Installation

```bash
claude plugin install odoo
```

## Skills

| Skill | Description |
|-------|-------------|
| **odooly** | Query and inspect Odoo data using odooly CLI |

## Usage

```text
/odoo:odooly search partners named John
/odoo:odooly show sale orders in state done
/odoo:odooly list products with name containing "cable"
/odoo:odooly compare access rights between 2 envs
```

Or simply ask to query Odoo data in natural language:

```text
"Show me all sale orders from partner Trobz"
"Find the partner with email john@example.com"
"Get product details for ID 42"
```
