# OCA Plugin

OCA (Odoo Community Association) toolkit: scaffold new modules, audit existing modules, and update OCA repositories from the upstream template.

## Requirements

- `gh` CLI authenticated (`gh auth login`)
- `copier` installed (for `repo-update` skill)

## Installation

```bash
claude plugin install oca
```

## Skills

| Skill | Description |
|-------|-------------|
| **new-module** | Scaffold a new OCA-compliant Odoo module |
| **audit-module** | Audit an existing module against OCA conventions |
| **repo-update** | Update an OCA repository from the upstream copier template |

## Usage

### Scaffold a new module

```text
/oca:new-module sale_custom_approval
/oca:new-module sale_custom_approval --version 18.0
/oca:new-module hr_attendance_ext --version 17.0 --path ./addons
/oca:new-module crm_lead_scoring --version 19.0 --app --features mail
/oca:new-module sale_portal_custom --version 18.0 --features mail,portal --no-demo
```

### Audit an existing module

```text
/oca:audit-module ./sale_custom_approval
/oca:audit-module ../addons/hr_attendance_ext --version 17.0
/oca:audit-module .
```

### Update OCA repo template

```text
/oca:repo-update
```

## Supported Odoo Versions

| Version | Notable Differences |
|---|---|
| `16.0` | `<tree>` tag, full chatter div, `/** @odoo-module */` JS header required |
| `17.0` | `attrs` removed; `/** @odoo-module */` still required; `_compute_display_name` preferred |
| `18.0` | `<list>` tag, `<chatter/>`, `check_access()`, `aggregator` attr |
| `19.0` | `models.Constraint`, `self.env.cr/uid`, `group_ids`, `type='jsonrpc'` routes |
