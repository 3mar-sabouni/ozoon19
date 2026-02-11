# -*- coding: utf-8 -*-
{
    'name': 'POS Z Report || POS Session Report || POS Session Z Report || Session Cash In Out',
    'author': 'OMAX Informatics',
    'version': '19.0.1.0',
    'website': 'www.omaxinformatics.com',
    'category': 'Point Of Sale',
    'description': """
    	POS Z Report || POS Session Report || POS Session Z Report
    """,
    'depends': [
        'base',
        'point_of_sale','pos_multiple_currencies'
    ],
    'data': [
        'report/report_pos_session.xml',
        'views/pos_session_view.xml',
    ],
    'demo': [],
    'test':[],
    'images': ['static/description/banner.jpg',],
    'license': 'OPL-1',
    'currency':'USD',
    'price': 7.0,
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_session_z_report_omax/static/src/overrides/components/control_buttons/control_buttons.js',
            'pos_session_z_report_omax/static/src/overrides/components/control_buttons/control_buttons.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'pre_init_hook': 'pre_init_check',
    'module_type': 'official',
    'summary': """
POS Z Receipt,POS Session Receipt,POS Session Z Receipt,POS Z Report,POS Session Report,POS Session Z Report,Point Of Sale Session Report,Session Receipt,Category Wise Sales,POS Session Taxes Detail,Session Taxes Detail,Session Pricelist Detail,Pricelist Detail,POS Session Pricelist Detail,POS Payment Detail,Payment Detail,Point Of Sale Payment Detail,Point Of Sale Cash In Out,Point Of Sale Cash In-Out,Point Of Sale Cash In/Out,POS Cash In Out,POS Cash In-Out,POS Cash In/Out,POS Cash In Out Receipt,POS Cash In-Out Receipt,POS Cash In/Out Receipt,POS Cash In Out Report,POS Cash In-Out Report,POS Cash In/Out Report,POS Cash Control,Point Of Sale Cash Control,Cash Control Report,Pos Cash In Out - Odoo,Put Money In,Take Money Out POS Cash register Z-Report
Point of Sale Z Report Z Report generation in POS Creating Z Reports in Point of Sale End-of-day POS report Daily sales report in POS Closing report for POS session POS day-end summary Summary report for POS session Z Summary in POS POS session closing report POS session sales summary Daily sales recap in POS Z Report sales overview 
Cash Register Closure Report Cash register closure in POS Closing report for cash register Daily cash register summary Z Report for cash register closure Shift End Report in POS POS shift end report End-of-shift report in Point of Sale Z Report for shift closure Closing summary for POS shift Financial Summary in POS Financial summary in Point of Sale Z Report financial overview POS session financial report Daily financial summary in POS Revenue Summary Report Revenue summary in POS Daily revenue report in Point of Sale Z Report revenue overview POS session revenue summary POS Closing Statement Closing statement in POS POS session closing details Z Report closing statement End-of-day statement in Point of Sale POS Cash Drawer Report Cash drawer report in POS Z Report for cash drawer Closing report for cash drawer in POS Daily cash drawer summary    
    """,
}
