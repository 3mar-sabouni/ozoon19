# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

{
    'name': "POS Multi Currency Payment",
    'summary': 'User can do payment in multiple-currency on POS Screen Pos Multi Currency provide a multi-currency facility to your customers in POS.Multi Currency|Payment In Multi Currency|Currency|Multiple currency POS Multi currency payment point of sales multi currency payment POS Multiple Currency payment pos payment different currency allow multi currency payment on POS MultiCurrency payment in Point of Sale MultiCurrency payment pos pay order with different two currency pos Payment Multi Currency payment on pos POS Multi Currency Payment POS multi currency  POS multiple currencies  Point of Sale foreign currency  POS accept multiple currencies  Odoo POS payment currencies  POS cash multi currency  POS international payments  POS multiple currency support  Odoo multi currency POS  POS global currency  POS foreign exchange  POS multi currency payments  POS different currencies The Point of Sale (POS) system allows users to process payments in multiple currencies directly from the POS screen. Key features include support for POS multi-currency payments, seamless currency conversion, and flexible payment methods such as cash and bank transactions. Users can configure multi-currency settings, manage currency rates (including automatic updates), and enable partial payments. The system provides a multi-currency button and popup for easy selection, along with a payment tab to view payment lines and history. Additional functionalities include generating order receipts, creating invoices via an invoice button, and validating transactions. The backend tracks payment history and integrates with accounting, while the product screen supports currency rate changes for accurate transactions.Multi-currency payments, POS Currency conversion, Currency management, Point of sale currency, Currency selection, International sales, Multi-currency transactions, Foreign currency payments, Multicurrency POS, Multiple currency, Cross-border money, Convert foreign currency.',
    'description': """
        The User will get the option to pay in multiple-currency on the PaymentScreen.
        This payment in multi-currency will be reflected on receipt as well as backend.
    """,
    'category': 'Point Of Sale',
    'version': '19.0.0.0',
    'depends': ['point_of_sale'],
    'data': [
        'views/res_config_settings.xml',
        'views/pos_order_view.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_multiple_currencies/static/src/js/pos_store.js',
            'pos_multiple_currencies/static/src/js/Popups/MultiCurrencyPopup.js',
            'pos_multiple_currencies/static/src/js/Popups/closing_popup.js',
            'pos_multiple_currencies/static/src/xml/MultiCurrencyPopup.xml',
            'pos_multiple_currencies/static/src/js/PaymentScreen/payment_screen.js',
            'pos_multiple_currencies/static/src/xml/OrderReciept.xml',
            'pos_multiple_currencies/static/src/xml/PaymentScreen.xml',
            'pos_multiple_currencies/static/src/xml/closing_popup.xml',
            'pos_multiple_currencies/static/src/css/style.css',
        ],
    },
    'author': 'Odoo DevHouse',
    'website': "https://apps.odoo.com/apps/modules/browse?author=Odoo%20DevHouse",
    "installable": True,
    'price': 35,
    'currency': 'USD',
    'application':True,
    'images': ['static/description/main_screenshot.png'],
    "license": "OPL-1",
}
