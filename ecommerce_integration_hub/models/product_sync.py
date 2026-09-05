from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _scope_covers(parent_record, child_record):
    """Whether parent's publication instance scope covers child's scope.

    Empty instance selection means ALL instances. Therefore:
    - parent empty => covers everything
    - child empty + parent explicit => parent does not cover child
    - both explicit => child must be a subset of parent
    """
    if not parent_record.ecommerce_integration_publish:
        return False
    parent_instances = parent_record.ecommerce_integration_instance_ids
    child_instances = child_record.ecommerce_integration_instance_ids
    if not parent_instances:
        return True
    if not child_instances:
        return False
    return not bool(child_instances - parent_instances)


class ProductCategory(models.Model):
    _inherit = "product.category"

    ecommerce_integration_publish = fields.Boolean(
        string="Publish to Ecommerce",
        default=False,
        copy=False,
        index=True,
        help=(
            "Enable ecommerce synchronization for this category. "
            "If Ecommerce Instances is empty, the category is published to every active instance."
        ),
    )
    ecommerce_integration_instance_ids = fields.Many2many(
        "ecommerce.integration.instance",
        "ecommerce_integration_product_category_instance_rel",
        "category_id",
        "instance_id",
        string="Ecommerce Instances",
        copy=False,
        domain="[('active', '=', True)]",
        help="Optional scope. Leave empty to publish to all active ecommerce instances.",
    )

    def _ecommerce_target_instances(self, auto_field=None):
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

    def _ecommerce_enqueue_category_sync(self):
        if self.env.context.get("ecommerce_skip_enqueue"):
            return
        Queue = self.env["ecommerce.integration.queue"].sudo()
        for category in self:
            for instance in category._ecommerce_target_instances("auto_sync_category"):
                Queue.enqueue(instance, "category", category, priority=10)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ecommerce_enqueue_category_sync()
        return records

    def write(self, vals):
        result = super().write(vals)
        relevant = {
            "name",
            "parent_id",
            "ecommerce_integration_publish",
            "ecommerce_integration_instance_ids",
        }
        if relevant.intersection(vals):
            self._ecommerce_enqueue_category_sync()
        return result

    @api.constrains("ecommerce_integration_publish", "ecommerce_integration_instance_ids", "parent_id")
    def _check_ecommerce_publication_scope(self):
        for category in self:
            if category.parent_id and category.ecommerce_integration_publish:
                if not _scope_covers(category.parent_id, category):
                    raise ValidationError(
                        _(
                            "Parent category '%(parent)s' must be published to a scope that covers category "
                            "'%(category)s'. Empty Ecommerce Instances means all instances.",
                            parent=category.parent_id.display_name,
                            category=category.display_name,
                        )
                    )

            for child in category.child_id.filtered("ecommerce_integration_publish"):
                if not _scope_covers(category, child):
                    raise ValidationError(
                        _(
                            "Category '%(category)s' must remain published to a scope that covers child "
                            "category '%(child)s'. Empty Ecommerce Instances means all instances.",
                            category=category.display_name,
                            child=child.display_name,
                        )
                    )

    def action_ecommerce_publish_to_ecommerce(self):
        self.write({"ecommerce_integration_publish": True})
        return True


class ProductTemplate(models.Model):
    _inherit = "product.template"

    ecommerce_integration_publish = fields.Boolean(
        string="Publish to Ecommerce",
        default=False,
        copy=False,
        index=True,
        help=(
            "Enable ecommerce synchronization for this product template and all of its Odoo variants. "
            "If Ecommerce Instances is empty, it is published to every active instance compatible with "
            "the product company."
        ),
    )
    ecommerce_integration_instance_ids = fields.Many2many(
        "ecommerce.integration.instance",
        "ecommerce_integration_product_template_instance_rel",
        "product_tmpl_id",
        "instance_id",
        string="Ecommerce Instances",
        copy=False,
        domain="[('active', '=', True)]",
        help=(
            "Optional scope. Leave empty to publish to all active ecommerce instances compatible with "
            "the product company."
        ),
    )

    def _ecommerce_target_instances(self, auto_field=None):
        self.ensure_one()
        if not self.ecommerce_integration_publish:
            return self.env["ecommerce.integration.instance"]
        domain = [("active", "=", True)]
        if auto_field:
            domain.append((auto_field, "=", True))
        if self.company_id:
            domain.append(("company_id", "=", self.company_id.id))
        instances = self.env["ecommerce.integration.instance"].sudo().search(domain)
        if self.ecommerce_integration_instance_ids:
            instances &= self.ecommerce_integration_instance_ids
        return instances

    def _ecommerce_enqueue_product_sync(self):
        if self.env.context.get("ecommerce_skip_enqueue"):
            return
        Queue = self.env["ecommerce.integration.queue"].sudo()
        for template in self:
            for instance in template._ecommerce_target_instances("auto_sync_product"):
                if instance._template_should_sync(template):
                    Queue.enqueue(instance, "product", template, priority=30)

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._ecommerce_enqueue_product_sync()
        return templates

    def write(self, vals):
        result = super().write(vals)
        relevant = {
            "name",
            "list_price",
            "categ_id",
            "attribute_line_ids",
            "image_1920",
            "active",
            "sale_ok",
            "company_id",
            "ecommerce_integration_publish",
            "ecommerce_integration_instance_ids",
        }
        if relevant.intersection(vals):
            self._ecommerce_enqueue_product_sync()
        return result

    @api.constrains(
        "ecommerce_integration_publish",
        "ecommerce_integration_instance_ids",
        "categ_id",
        "company_id",
    )
    def _check_ecommerce_publication_scope(self):
        for template in self:
            if not template.ecommerce_integration_publish:
                continue

            wrong_company = template.ecommerce_integration_instance_ids.filtered(
                lambda instance: template.company_id and instance.company_id != template.company_id
            )
            if wrong_company:
                raise ValidationError(
                    _(
                        "Product '%(product)s' belongs to %(company)s and cannot be published to instances of "
                        "another company: %(instances)s.",
                        product=template.display_name,
                        company=template.company_id.display_name,
                        instances=", ".join(wrong_company.mapped("display_name")),
                    )
                )

            category = template.categ_id
            if category and not _scope_covers(category, template):
                raise ValidationError(
                    _(
                        "Product category '%(category)s' must be published to a scope that covers product "
                        "'%(product)s'. Empty Ecommerce Instances means all instances.",
                        category=category.display_name,
                        product=template.display_name,
                    )
                )

    def action_ecommerce_publish_to_ecommerce(self):
        self.write({"ecommerce_integration_publish": True})
        return True


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _ecommerce_enqueue_template_sync(self):
        self.mapped("product_tmpl_id")._ecommerce_enqueue_product_sync()

    @api.model_create_multi
    def create(self, vals_list):
        variants = super().create(vals_list)
        variants._ecommerce_enqueue_template_sync()
        return variants

    def write(self, vals):
        result = super().write(vals)
        if {"barcode", "default_code", "active", "product_template_attribute_value_ids"}.intersection(vals):
            self._ecommerce_enqueue_template_sync()
        return result

    def action_ecommerce_publish_to_ecommerce(self):
        self.mapped("product_tmpl_id").action_ecommerce_publish_to_ecommerce()
        return True
