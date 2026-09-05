from odoo import _, fields, models
from odoo.exceptions import ValidationError


class EcommerceIntegrationClearLogsWizard(models.TransientModel):
    _name = "ecommerce.integration.clear.logs.wizard"
    _description = "Clear Ecommerce Sync Transactions"

    instance_id = fields.Many2one("ecommerce.integration.instance", required=True)
    scope = fields.Selection(
        [
            ("logs", "Logs only"),
            ("history", "Logs + completed/failed queue history"),
            ("all_queue", "Logs + all queue records, including pending work"),
        ],
        default="history",
        required=True,
    )
    confirm = fields.Boolean(string="I understand this clears connector transaction history")

    def action_clear(self):
        self.ensure_one()
        if not self.confirm:
            raise ValidationError(_("Confirm the cleanup before continuing."))

        instance = self.instance_id
        self.env["ecommerce.integration.log"].search([("instance_id", "=", instance.id)]).unlink()
        if self.scope == "history":
            self.env["ecommerce.integration.queue"].search(
                [("instance_id", "=", instance.id), ("state", "in", ["done", "failed"])]
            ).unlink()
        elif self.scope == "all_queue":
            self.env["ecommerce.integration.queue"].search([("instance_id", "=", instance.id)]).unlink()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Connector History Cleared"),
                "message": _("Bindings and Odoo business records were not deleted."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
