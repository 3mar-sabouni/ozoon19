{
    'name': 'POS Product Exchange',

    'summary': 'Allow product exchange directly in Point of Sale',

    'description': """
3s POS Product Exchange enables cashiers to exchange products directly
within the Odoo Point of Sale interface.
    """,

    'author': 'My Company',
    'website': 'https://www.yourcompany.com',

    'category': 'Point of Sale',
    'version': '19.0.0.1.0',
    'depends': ['point_of_sale'],
    'data': ['views/pos_config_view.xml'],
    'assets': {
        "point_of_sale._assets_pos": [
            "3s_pos_exchange/static/src/js/exchange_button.js",
            "3s_pos_exchange/static/src/js/exchange_screen.js",
            "3s_pos_exchange/static/src/js/exchange_popup.js",
           # "3s_pos_exchange/static/src/js/pos_auto_global_discount.js",
            "3s_pos_exchange/static/src/xml/exchange_button.xml",
            "3s_pos_exchange/static/src/xml/exchange_screen.xml",
            "3s_pos_exchange/static/src/xml/exchange_popup.xml",
        ],
    },
    'application': False,
    'license': 'LGPL-3',
}
