from odoo import api, fields, models


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    ecommerce_integration_publish = fields.Boolean(
        string="Publish to Ecommerce",
        default=False,
        copy=False,
        index=True,
        help=(
            "Enable ecommerce synchronization for this attribute and all of its values. "
            "If Ecommerce Instances is empty, the attribute is published to every active instance."
        ),
    )
    ecommerce_integration_instance_ids = fields.Many2many(
        "ecommerce.integration.instance",
        "ecommerce_integration_product_attribute_instance_rel",
        "attribute_id",
        "instance_id",
        string="Ecommerce Instances",
        copy=False,
        domain="[('active', '=', True)]",
        help="Optional scope. Leave empty to publish this attribute and all its values to all active instances.",
    )

    def _ecommerce_target_instances(self, auto_field=None):
        """Return active instances in this attribute's publication scope.

        Empty ecommerce_integration_instance_ids deliberately means all active instances.
        """
        self.ensure_one()
        if not self.ecommerce_integration_publish:
            return self.env["ecommerce.integration.instance"]
        domain = [("active", "=", True)]
        if auto_field:
            domain.append((auto_field, "=", True))
        instances = self.env["ecommerce.integration.instance"].sudo().search(domain)
        if self.ecommerce_integration_instance_ids:
            instances &= self.ecommerce_integration_instance_ids
        return instances

    def _ecommerce_enqueue_attribute_sync(self):
        if self.env.context.get("ecommerce_skip_enqueue"):
            return
        Queue = self.env["ecommerce.integration.queue"].sudo()
        for attribute in self:
            for instance in attribute._ecommerce_target_instances("auto_sync_product"):
                Queue.enqueue(instance, "attribute", attribute, priority=20)

    def _ecommerce_enqueue_affected_products(self):
        templates = self.mapped("product_tmpl_ids")
        if templates:
            templates._ecommerce_enqueue_product_sync()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ecommerce_enqueue_attribute_sync()
        records._ecommerce_enqueue_affected_products()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {
            "name",
            "active",
            "sequence",
            "create_variant",
            "display_type",
            "ecommerce_integration_publish",
            "ecommerce_integration_instance_ids",
        }.intersection(vals):
            self._ecommerce_enqueue_attribute_sync()
            self._ecommerce_enqueue_affected_products()
        return result

    def action_ecommerce_publish_to_ecommerce(self):
        """List-view bulk action. Existing instance restrictions are preserved.

        Records with no selected instances become published to all active instances.
        """
        self.write({"ecommerce_integration_publish": True})
        return True


class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"

    def _ecommerce_affected_templates(self):
        return self.mapped("pav_attribute_line_ids.product_tmpl_id")

    def _ecommerce_enqueue_parent_and_products(self, attributes=None, templates=None):
        attributes = attributes or self.mapped("attribute_id")
        templates = templates or self._ecommerce_affected_templates()
        if attributes:
            attributes._ecommerce_enqueue_attribute_sync()
        if templates:
            templates._ecommerce_enqueue_product_sync()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ecommerce_enqueue_parent_and_products()
        return records

    def write(self, vals):
        before_attributes = self.mapped("attribute_id")
        before_templates = self._ecommerce_affected_templates()
        result = super().write(vals)
        if {"name", "active", "sequence", "attribute_id"}.intersection(vals):
            self._ecommerce_enqueue_parent_and_products(
                before_attributes | self.mapped("attribute_id"),
                before_templates | self._ecommerce_affected_templates(),
            )
        return result

    def unlink(self):
        attributes = self.mapped("attribute_id")
        templates = self._ecommerce_affected_templates()
        result = super().unlink()
        if attributes:
            attributes._ecommerce_enqueue_attribute_sync()
        if templates:
            templates._ecommerce_enqueue_product_sync()
        return result


class ProductTemplateAttributeLine(models.Model):
    _inherit = "product.template.attribute.line"

    def _ecommerce_enqueue_templates(self, templates=None):
        (templates or self.mapped("product_tmpl_id"))._ecommerce_enqueue_product_sync()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ecommerce_enqueue_templates()
        return records

    def write(self, vals):
        before = self.mapped("product_tmpl_id")
        result = super().write(vals)
        self._ecommerce_enqueue_templates(before | self.mapped("product_tmpl_id"))
        return result

    def unlink(self):
        templates = self.mapped("product_tmpl_id")
        result = super().unlink()
        templates._ecommerce_enqueue_product_sync()
        return result


class ProductTemplateAttributeValue(models.Model):
    _inherit = "product.template.attribute.value"

    def write(self, vals):
        templates = self.mapped("product_tmpl_id")
        result = super().write(vals)
        if {"price_extra", "ptav_active"}.intersection(vals):
            templates._ecommerce_enqueue_product_sync()
        return result
