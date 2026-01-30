# -*- coding: utf-8 -*-
{
    "name": "POS Order Item and Qty Count",
    "summary": "Display total order items and quantity on POS screen and receipt",
    "description": """
        This module displays the total number of order items and the total quantity
        in the Point of Sale screen and on the POS receipt.
        
        It helps cashiers quickly understand order size, improves billing accuracy,
        and provides clear order information to customers.
        
        The item and quantity counts are updated in real time as products are added,
        removed, or their quantities are changed, without affecting the existing
        POS workflow.
    """,
    "author": "CodeSphere Tech",
    "website": "https://www.codespheretech.in/",
    "category": "Point of Sale",
    "version": "19.0.1.0.0",
    "sequence": 0,
    "currency": "USD",
    "price": "0",
    "depends": ["base", "point_of_sale", ],
    "data": [],
    "assets": {
        'point_of_sale._assets_pos': [
            'cst_pos_order_lines_count/static/src/**/*',
        ],
    },
    "images": ["static/description/Banner.png"],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
