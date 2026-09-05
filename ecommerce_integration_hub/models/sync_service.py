from odoo import _, fields, models

from .common import DependencyPending, PermanentConnectorError


class EcommerceIntegrationInstanceSyncService(models.Model):
    _inherit = "ecommerce.integration.instance"

    def _binding(self, record, *, handle_seed=None):
        self.ensure_one()
        return self.env["ecommerce.integration.binding"].get_or_create(
            self,
            record,
            handle_seed=handle_seed,
        )

    def _is_published_to_instance(self, record):
        self.ensure_one()
        instances = getattr(record, "ecommerce_integration_instance_ids", self.env["ecommerce.integration.instance"])
        return bool(
            getattr(record, "ecommerce_integration_publish", False)
            and (not instances or self.id in instances.ids)
        )

    def _category_should_sync(self, category):
        self.ensure_one()
        return bool(category and self._is_published_to_instance(category))

    def _template_is_for_instance(self, template):
        self.ensure_one()
        if template.company_id and template.company_id != self.company_id:
            return False
        return self._is_published_to_instance(template)

    def _template_should_sync(self, template):
        """Return whether a template is currently in this instance's outbound publication scope."""
        self.ensure_one()
        return bool(
            self._template_is_for_instance(template)
            and template.active
            and template.sale_ok
        )

    def _attribute_should_sync(self, attribute):
        self.ensure_one()
        return bool(attribute and self._is_published_to_instance(attribute))


    def _prepare_category_payload(self, category):
        """Build an order-independent category payload.

        Category synchronization must never depend on the parent having been sent
        first.  The receiver can create/update the category immediately using the
        stable Odoo category IDs, then attach the hierarchy once the parent exists.
        If the parent is already bound we also include its external ID as a useful
        shortcut for the receiver.
        """
        self.ensure_one()
        binding = self._binding(category, handle_seed=category.name)

        parent = category.parent_id
        parent_binding = False
        parent_external_id = False
        parent_handle = False
        if parent:
            parent_binding = self._binding(parent, handle_seed=parent.name)
            parent_external_id = parent_binding.external_id or False
            parent_handle = parent_binding.handle or False

        payload = {
            "odoo_category_id": category.id,
            "name": category.name,
            "handle": binding.handle,
            "parent_odoo_category_id": parent.id if parent else None,
            "parent_external_id": parent_external_id,
            "parent_handle": parent_handle,
        }
        translations = self._translations(category, "name", "name")
        if translations:
            payload["translations"] = translations
        return payload, binding

    def _sync_category(self, category):
        self.ensure_one()
        if not self._category_should_sync(category):
            raise PermanentConnectorError(
                _("Category '%s' is not published to this ecommerce instance.") % category.display_name
            )
        payload, binding = self._prepare_category_payload(category)
        response, http_status, duration_ms = self._request_json(self.category_endpoint, payload)
        if response.get("status") not in {"created", "updated"}:
            binding.write({"sync_state": "error", "last_error": str(response)})
            raise PermanentConnectorError(_("Category response reported an error: %s") % response)
        binding.write(
            {
                "external_id": response.get("external_category_id") or response.get("category_id") or binding.external_id,
                "sync_state": "synced",
                "last_sync_at": fields.Datetime.now(),
                "last_error": False,
            }
        )

        # Hierarchy reconciliation pass: if a child was sent before this parent,
        # send the child again now that the parent has an external binding.  This
        # makes category sync converge correctly without enforcing queue order.
        Queue = self.env["ecommerce.integration.queue"]
        for child in category.child_id.filtered(lambda item: self._category_should_sync(item)):
            Queue.enqueue(self, "category", child, priority=10)

        return payload, response, http_status, duration_ms

    def _variant_option_label(self, variant, variant_attributes):
        ptavs = variant.product_template_attribute_value_ids.filtered(
            lambda value: value.attribute_id in variant_attributes
        ).sorted(key=lambda value: (value.attribute_id.sequence, value.attribute_id.id, value.id))
        if len(variant_attributes) == 1:
            return ptavs[:1].name or _("Default")
        return " / ".join(f"{value.attribute_id.name}: {value.name}" for value in ptavs) or _("Default")

    def _variant_option_map(self, variant, variant_attributes):
        """Return the option values for exactly this sellable Odoo variant."""
        values = variant.product_template_attribute_value_ids.filtered(
            lambda value: value.attribute_id in variant_attributes
        ).sorted(key=lambda value: (value.attribute_id.sequence, value.attribute_id.id, value.id))
        return {value.attribute_id.name: value.name for value in values}

    def _native_product_options(self, variants, variant_attributes):
        """Build ordered option groups while keeping availability at variant level."""
        options = []
        for attribute in variant_attributes.sorted(key=lambda item: (item.sequence, item.id)):
            values = []
            for variant in variants.sorted("id"):
                option_map = self._variant_option_map(variant, variant_attributes)
                value = option_map.get(attribute.name)
                if value and value not in values:
                    values.append(value)
            options.append({"name": attribute.name, "values": values})
        return options

    def _validate_variant_publication(self, template, variant_attributes):
        self.ensure_one()
        unpublished_attributes = variant_attributes.filtered(
            lambda attribute: not self._attribute_should_sync(attribute)
        )
        if unpublished_attributes:
            raise PermanentConnectorError(
                _(
                    "Product '%(product)s' uses attributes that are not published to instance '%(instance)s': "
                    "%(attributes)s.",
                    product=template.display_name,
                    instance=self.display_name,
                    attributes=", ".join(unpublished_attributes.mapped("display_name")),
                )
            )

    def _prepare_product_payload(self, template):
        self.ensure_one()
        if not self._template_should_sync(template):
            raise PermanentConnectorError(
                _("Product '%s' is not published to this ecommerce instance.") % template.display_name
            )

        binding = self._binding(template, handle_seed=template.name)
        category = template.categ_id
        categories = self.env["product.category"]
        if category:
            if not self._category_should_sync(category):
                raise PermanentConnectorError(
                    _(
                        "Product category '%(category)s' is not published to ecommerce instance '%(instance)s'.",
                        category=category.display_name,
                        instance=self.display_name,
                    )
                )
            categories |= category

        missing_categories = self.env["product.category"]
        for item in categories:
            category_binding = self._binding(item, handle_seed=item.name)
            if category_binding.sync_state != "synced":
                missing_categories |= item
        if missing_categories:
            for item in missing_categories.sorted(
                key=lambda cat: (len((cat.parent_path or "").split("/")), cat.id)
            ):
                self.env["ecommerce.integration.queue"].enqueue(self, "category", item, priority=5)
            raise DependencyPending(
                _("Product categories must be synchronized before product '%s'.") % template.display_name
            )

        variants = template.product_variant_ids.filtered("active")
        if not variants:
            raise PermanentConnectorError(
                _("Product '%s' has no active Odoo variants to synchronize.") % template.display_name
            )

        variant_attributes = template.valid_product_template_attribute_line_ids.mapped("attribute_id").filtered(
            lambda attribute: attribute.create_variant != "no_variant"
        )
        self._validate_variant_publication(template, variant_attributes)

        quantities = self._variant_quantities(variants)
        variant_payloads = []

        if self.multi_attribute_mode == "flatten" and variant_attributes:
            flattened_values = []
            for variant in variants.sorted("id"):
                label = self._variant_option_label(variant, variant_attributes)
                if label not in flattened_values:
                    flattened_values.append(label)
                variant_payloads.append(
                    {
                        "odoo_variant_id": variant.id,
                        "sku": self._variant_identifier(variant),
                        "title": label,
                        "options": {"Variant": label},
                        "price": self._variant_price(variant),
                        "quantity": quantities.get(variant.id, 0.0),
                    }
                )
            product_options = [{"name": "Variant", "values": flattened_values}]
        else:
            product_options = self._native_product_options(variants, variant_attributes) if variant_attributes else []
            for variant in variants.sorted("id"):
                option_map = self._variant_option_map(variant, variant_attributes) if variant_attributes else {}
                variant_payloads.append(
                    {
                        "odoo_variant_id": variant.id,
                        "sku": self._variant_identifier(variant),
                        "title": self._variant_option_label(variant, variant_attributes) if variant_attributes else _("Default"),
                        "options": option_map,
                        "price": self._variant_price(variant),
                        "quantity": quantities.get(variant.id, 0.0),
                    }
                )

        payload = {
            "odoo_template_id": template.id,
            "title": template.name,
            "handle": binding.handle,
            "odoo_category_ids": categories.ids,
            "options": product_options,
            "currency": self.target_currency_id.name,
            "variants": variant_payloads,
        }
        image_url = self._image_url(template)
        if image_url:
            payload["image_url"] = image_url
        translations = self._translations(template, "name", "title")
        if translations:
            payload["translations"] = translations
        return payload, binding, variants

    def _sync_product(self, template):
        self.ensure_one()
        payload, binding, variants = self._prepare_product_payload(template)
        response, http_status, duration_ms = self._request_json(self.product_endpoint, payload)
        if response.get("status") not in {"created", "updated"}:
            binding.write({"sync_state": "error", "last_error": str(response)})
            raise PermanentConnectorError(_("Product response reported an error: %s") % response)

        response_variants = {
            item.get("odoo_variant_id"): item
            for item in response.get("variants", [])
            if item.get("odoo_variant_id")
        }
        variant_errors = []
        for variant in variants:
            item = response_variants.get(variant.id)
            variant_binding = self._binding(variant)
            if not item or item.get("status") not in {"created", "updated"}:
                reason = (item or {}).get("reason") or _("Missing or invalid variant result from the remote API.")
                variant_binding.write({"sync_state": "error", "last_error": reason})
                variant_errors.append(
                    _("Variant %(variant)s: %(reason)s", variant=variant.display_name, reason=reason)
                )
                continue
            variant_binding.write(
                {
                    "external_id": item.get("external_variant_id") or item.get("variant_id") or variant_binding.external_id,
                    "sync_state": "synced",
                    "last_sync_at": fields.Datetime.now(),
                    "last_error": False,
                }
            )

        if variant_errors:
            error_message = "\n".join(variant_errors)
            binding.write(
                {
                    "external_id": response.get("external_product_id") or response.get("product_id") or binding.external_id,
                    "sync_state": "error",
                    "last_error": error_message,
                }
            )
            raise PermanentConnectorError(
                _("Product response contained variant errors:\n%s") % error_message,
                status_code=http_status,
                response_text=self.json_text(response),
            )

        binding.write(
            {
                "external_id": response.get("external_product_id") or response.get("product_id") or binding.external_id,
                "sync_state": "synced",
                "last_sync_at": fields.Datetime.now(),
                "last_error": False,
            }
        )
        return payload, response, http_status, duration_ms

    def _sync_attribute_local(self, attribute):
        """The current API has no standalone attribute route; propagate to affected products."""
        self.ensure_one()
        if not self._attribute_should_sync(attribute):
            raise PermanentConnectorError(
                _("Attribute '%s' is not published to this ecommerce instance.") % attribute.display_name
            )
        binding = self._binding(attribute)
        templates = attribute.product_tmpl_ids.filtered(self._template_should_sync)
        for template in templates:
            self.env["ecommerce.integration.queue"].enqueue(self, "product", template, priority=30)
        binding.write(
            {
                "sync_state": "synced",
                "last_sync_at": fields.Datetime.now(),
                "last_error": False,
            }
        )
        payload = {
            "odoo_attribute_id": attribute.id,
            "name": attribute.name,
            "value_ids": attribute.value_ids.ids,
        }
        response = {
            "status": "embedded",
            "reason": "Attribute changes are embedded in product/variant payloads; affected products were queued.",
            "queued_product_count": len(templates),
        }
        return payload, response, None, 0
