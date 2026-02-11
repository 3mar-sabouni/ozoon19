# -*- coding: utf-8 -*-
from . import models
from . import report

def pre_init_check(cr):
    from odoo.service import common
    from odoo.exceptions import ValidationError
    version_info = common.exp_version()
    server_serie = version_info.get('server_serie')
    server_version = version_info.get('server_version', '')
    if not server_version.startswith('19.'):
        raise ValidationError('This module supports Odoo 19.x series. Your Odoo version is {}.'.format(server_version))
    return True

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
