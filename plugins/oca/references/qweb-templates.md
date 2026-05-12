# QWeb Templates Reference

Guide for creating QWeb report templates, portal/website templates, and OWL component templates.

---

## QWeb Directives

| Directive | Use | Notes |
|---|---|---|
| `t-out="expr"` | Render value (HTML-escaped) | **Preferred** in all versions |
| `t-field="record.field"` | Render model field with proper widget | Use in report/portal templates |
| `t-esc="expr"` | Render value (HTML-escaped) | **Deprecated** — use `t-out` |
| `t-raw="expr"` | Render raw HTML | **Deprecated** — use `t-out` with `Markup` |
| `t-if` / `t-elif` / `t-else` | Conditional rendering | — |
| `t-foreach="list" t-as="item"` | Loop | — |
| `t-set="var" t-value="expr"` | Set local variable | — |
| `t-call="template_id"` | Include another template | — |
| `t-att-<attr>="expr"` | Dynamic HTML attribute | e.g., `t-att-href="url"` |

---

## QWeb PDF Report

### 1. Report Action (`report/<report_name>.xml`)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Report action -->
    <record id="action_report_<module_model>" model="ir.actions.report">
        <field name="name">My Report</field>
        <field name="model"><dot.notation.model></field>
        <field name="report_type">qweb-pdf</field>
        <field name="report_name"><module_name>.report_<module_model>_document</field>
        <field name="report_file"><module_name>.report_<module_model>_document</field>
        <field name="binding_model_id" ref="model_<module_model>"/>
        <field name="binding_type">report</field>
    </record>

    <!-- Main template: iterates over records -->
    <template id="report_<module_model>">
        <t t-call="web.html_container">
            <t t-foreach="docs" t-as="doc">
                <t t-call="<module_name>.report_<module_model>_document"
                   t-lang="doc.partner_id.lang"/>
            </t>
        </t>
    </template>

    <!-- Document template: single record layout -->
    <template id="report_<module_model>_document">
        <t t-call="web.external_layout">
            <div class="page">
                <div class="row">
                    <div class="col-6">
                        <strong>Reference:</strong>
                        <span t-field="doc.name"/>
                    </div>
                    <div class="col-6">
                        <strong>Date:</strong>
                        <span t-field="doc.date"/>
                    </div>
                </div>

                <table class="table table-sm mt-4">
                    <thead>
                        <tr>
                            <th>Description</th>
                            <th class="text-end">Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        <t t-foreach="doc.line_ids" t-as="line">
                            <tr>
                                <td><t t-out="line.name"/></td>
                                <td class="text-end"><t t-field="line.amount"/></td>
                            </tr>
                        </t>
                    </tbody>
                </table>
            </div>
        </t>
    </template>
</odoo>
```

Add to manifest `data`:

```python
"data": [
    ...
    "report/<report_name>.xml",
],
```

### 2. Paper Format (optional)

```xml
<record id="paperformat_<module_name>" model="report.paperformat">
    <field name="name">My Module Paper Format</field>
    <field name="default" eval="False"/>
    <field name="format">A4</field>
    <field name="page_height">0</field>
    <field name="page_width">0</field>
    <field name="orientation">Portrait</field>
    <field name="margin_top">40</field>
    <field name="margin_bottom">23</field>
    <field name="margin_left">7</field>
    <field name="margin_right">7</field>
    <field name="header_line" eval="False"/>
    <field name="header_spacing">35</field>
    <field name="dpi">90</field>
</record>
```

---

## Portal Template

### 1. Controller (`controllers/main.py`)

```python
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class MyModulePortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "my_record_count" in counters:
            values["my_record_count"] = request.env["<dot.notation.model>"].search_count([])
        return values

    @http.route(["/my/<module_name>", "/my/<module_name>/page/<int:page>"],
                type="http", auth="user", website=True)
    def portal_my_records(self, page=1, **kwargs):
        domain = []
        RecordModel = request.env["<dot.notation.model>"]
        record_count = RecordModel.search_count(domain)
        pager = portal_pager(
            url="/my/<module_name>",
            total=record_count,
            page=page,
            step=10,
        )
        records = RecordModel.search(domain, limit=10, offset=pager["offset"])
        return request.render("<module_name>.portal_my_<module_name>", {
            "records": records,
            "page_name": "<module_name>",
            "pager": pager,
        })
```

### 2. Portal List Template (`views/<module_name>_portal_templates.xml`)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Portal home counter -->
    <template id="portal_my_home_<module_name>" name="Portal My Home: <ModuleName>"
              inherit_id="portal.portal_my_home" priority="30">
        <xpath expr="//div[hasclass('o_portal_docs')]" position="inside">
            <t t-call="portal.portal_docs_entry">
                <t t-set="title">My Records</t>
                <t t-set="url">/my/<module_name></t>
                <t t-set="count" t-value="my_record_count"/>
            </t>
        </xpath>
    </template>

    <!-- Portal list page -->
    <template id="portal_my_<module_name>" name="My <ModuleName>">
        <t t-call="portal.portal_layout">
            <t t-set="breadcrumbs_searchbar" t-value="True"/>
            <t t-call="portal.portal_searchbar">
                <t t-set="title">My Records</t>
            </t>
            <t t-if="not records">
                <div class="alert alert-warning mt-3">
                    <p>No records found.</p>
                </div>
            </t>
            <t t-if="records" t-call="portal.portal_table">
                <thead>
                    <tr class="active">
                        <th>Reference</th>
                        <th class="text-end">Date</th>
                    </tr>
                </thead>
                <t t-foreach="records" t-as="record">
                    <tr>
                        <td>
                            <a t-att-href="record.get_portal_url()">
                                <t t-out="record.name"/>
                            </a>
                        </td>
                        <td class="text-end">
                            <span t-field="record.date"/>
                        </td>
                    </tr>
                </t>
            </t>
        </t>
    </template>
</odoo>
```

Add to manifest `data`:

```python
"data": [
    ...
    "views/<module_name>_portal_templates.xml",
],
```

---

## OWL Component Template (Backend Widget)

### Component JS (`static/src/components/<ComponentName>.js`)

```javascript
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class MyComponent extends Component {
    static template = "<module_name>.MyComponent";
    static props = {
        record: Object,
        readonly: { type: Boolean, optional: true },
    };

    setup() {
        this.state = useState({ isLoading: false });
    }

    async onActionClick() {
        this.state.isLoading = true;
        await this.props.record.save();
        this.state.isLoading = false;
    }
}

registry.category("fields").add("my_component", { component: MyComponent });
```

> **Note on `/** @odoo-module **/` header:**
>
> - v16.0: required at the top of every JS file
> - v17.0: required
> - v18.0+: **can be omitted** (ES module auto-detection via PR #142858)

### Component XML Template (`static/src/components/<ComponentName>.xml`)

```xml
<?xml version="1.0" encoding="utf-8"?>
<templates xml:space="preserve">
    <t t-name="<module_name>.MyComponent">
        <div class="o_my_component">
            <div t-if="state.isLoading" class="text-center">
                <i class="fa fa-spinner fa-spin"/>
            </div>
            <div t-else="">
                <button
                    class="btn btn-primary"
                    t-on-click="onActionClick"
                    t-att-disabled="props.readonly">
                    Confirm
                </button>
            </div>
        </div>
    </t>
</templates>
```

> **Note on `owl="1"` template attribute:**
>
> - v16.0: required on `<templates>` tag
> - v17.0+: **removed** — `<templates xml:space="preserve">` is sufficient

### Register in manifest assets

```python
"assets": {
    "web.assets_backend": [
        "<module_name>/static/src/components/**/*.js",
        "<module_name>/static/src/components/**/*.xml",
        "<module_name>/static/src/components/**/*.scss",
    ],
},
```
