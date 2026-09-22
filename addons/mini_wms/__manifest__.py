{
    "name": "Mini WMS",
    "version": "18.0.1.0.0",
    "category": "Inventory/Warehouse",
    "summary": "Mini Warehouse Management System for Odoo",
    "description": """
Mini Warehouse Management System for Odoo
==========================================
A custom Odoo 18 module for managing warehouses, stock locations, products,
receipts, internal transfers, customer shipments, and inventory adjustments.

Key Features:
-------------
* Multi-warehouse and hierarchical location management
* Ledger-based stock movement tracking (wms.stock.movement)
* Inbound receipts with automated numbering and stock posting
* Internal transfers with real-time location stock validation
* Outbound shipments with stock availability checks
* Inventory adjustments for stock reconciling
* Role-based access control (WMS User / WMS Manager)
* Smart buttons, statusbars, and automated low-stock warnings
    """,
    "author": "Mini WMS Team",
    "website": "https://github.com/example/mini_wms",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/warehouse_views.xml",
        "views/location_views.xml",
        "views/product_views.xml",
        "views/stock_receipt_views.xml",
        "views/stock_transfer_views.xml",
        "views/stock_shipment_views.xml",
        "views/stock_movement_views.xml",
        "views/inventory_adjustment_views.xml",
        "views/dashboard_views.xml",
        "views/menu_views.xml",
    ],
    "demo": [
        "demo/demo_data.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
