# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    is_multi_currency = fields.Boolean(
        related='config_id.multi_currency_payment', readonly=False
    )


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        params += ['inverse_rate']
        return params

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, load=False):
        if 'check_from_pos' in self.env.context:
            if 'config_id' in self.env.context:
                cr_id = self.env['pos.config'].browse(int(self.env.context.get('config_id'))).currency_id
                if cr_id:
                    domain = domain or []
                    found = False
                    for cond in domain:
                        if isinstance(cond, (list, tuple)) and len(cond) == 3 and cond[0] == 'id' and cond[1] == 'in':
                            cond[2].append(cr_id.id)
                            found = True
                            break
                    if not found:
                        domain.append(('id', 'in', [cr_id.id]))
            res = super(ResCurrency, self).search_read(
                domain=domain, fields=fields, offset=offset, limit=limit,
                order=order, load=load
            )
            for curr in res:
                currency_obj = self.browse([curr.get('id')]).rate_ids
                for currency in currency_obj:
                    formatted_inverse =   currency.company_rate
                    formatted_rate =  currency.inverse_company_rate
  
                    curr.update({
                        'rate': formatted_inverse,
                        'inverse_rate': formatted_rate  ,
                    }) 
            return res
        return super(ResCurrency, self).search_read(
            domain=domain, fields=fields, offset=offset, limit=limit,
            order=order, load=load
        )
