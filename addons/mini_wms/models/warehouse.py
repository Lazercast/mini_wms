from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WmsWarehouse(models.Model):
    _name = "wms.warehouse"
    _description = "Warehouse"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(
        string="Warehouse Name",
        required=True,
        tracking=True,
        help="Full human-readable name of the warehouse.",
    )
    code = fields.Char(
        string="Warehouse Code",
        required=True,
        size=10,
        tracking=True,
        help="Unique identifier or abbreviation for this warehouse (e.g. WH-MAIN, WH-AST).",
    )
    address = fields.Text(
        string="Address",
        help="Physical address and postal information of the facility.",
    )
    manager_id = fields.Many2one(
        comodel_name="res.users",
        string="Warehouse Manager",
        tracking=True,
        default=lambda self: self.env.user,
        help="The user responsible for operations in this warehouse.",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to archive the warehouse. Inactive warehouses cannot be used for new operations.",
    )
    notes = fields.Text(string="Notes")

    location_ids = fields.One2many(
        comodel_name="wms.location",
        inverse_name="warehouse_id",
        string="Locations",
        help="All physical and operational zones inside this warehouse.",
    )

    product_count = fields.Integer(
        string="Products in Stock",
        compute="_compute_product_count",
        help="Count of distinct products currently stored in this warehouse.",
    )

    _sql_constraints = [
        (
            "code_unique",
            "UNIQUE(code)",
            "The warehouse code must be unique! A warehouse with this code already exists.",
        ),
    ]

    @api.constrains("code")
    def _check_code(self):
        for warehouse in self:
            if not warehouse.code or not warehouse.code.strip():
                raise ValidationError(_("Warehouse code cannot be empty or whitespace."))

    def _compute_product_count(self):
        """
        Computes the number of unique active products that currently
        have positive stock within this warehouse.
        """
        for warehouse in self:
            if "wms.stock.movement" in self.env:
                wh_locations = warehouse.location_ids.ids
                if not wh_locations:
                    warehouse.product_count = 0
                    continue

                products = self.env["wms.product"].search([("active", "=", True)])
                count = 0
                for product in products:
                    in_qty = sum(self.env["wms.stock.movement"].search([
                        ("product_id", "=", product.id),
                        ("destination_location_id", "in", wh_locations),
                    ]).mapped("quantity"))
                    out_qty = sum(self.env["wms.stock.movement"].search([
                        ("product_id", "=", product.id),
                        ("source_location_id", "in", wh_locations),
                    ]).mapped("quantity"))
                    if (in_qty - out_qty) > 0:
                        count += 1
                warehouse.product_count = count
            else:
                warehouse.product_count = 0

    location_count = fields.Integer(
        string="Location Count",
        compute="_compute_counts",
    )
    receipt_count = fields.Integer(
        string="Receipt Count",
        compute="_compute_counts",
    )
    transfer_count = fields.Integer(
        string="Transfer Count",
        compute="_compute_counts",
    )
    shipment_count = fields.Integer(
        string="Shipment Count",
        compute="_compute_counts",
    )

    def _compute_counts(self):
        for wh in self:
            wh.location_count = self.env["wms.location"].search_count([("warehouse_id", "=", wh.id)])
            wh.receipt_count = self.env["wms.stock.receipt"].search_count([("warehouse_id", "=", wh.id)])
            wh.transfer_count = self.env["wms.stock.transfer"].search_count([("warehouse_id", "=", wh.id)])
            wh.shipment_count = self.env["wms.stock.shipment"].search_count([("warehouse_id", "=", wh.id)])

    def action_view_locations(self):
        self.ensure_one()
        return {
            "name": _("Locations"),
            "type": "ir.actions.act_window",
            "res_model": "wms.location",
            "view_mode": "list,form",
            "domain": [("warehouse_id", "=", self.id)],
            "context": {"default_warehouse_id": self.id},
        }

    def action_view_products(self):
        self.ensure_one()
        return {
            "name": _("Products"),
            "type": "ir.actions.act_window",
            "res_model": "wms.product",
            "view_mode": "kanban,list,form",
        }

    def action_view_receipts(self):
        self.ensure_one()
        return {
            "name": _("Receipts"),
            "type": "ir.actions.act_window",
            "res_model": "wms.stock.receipt",
            "view_mode": "list,form",
            "domain": [("warehouse_id", "=", self.id)],
            "context": {"default_warehouse_id": self.id},
        }

    def action_view_transfers(self):
        self.ensure_one()
        return {
            "name": _("Transfers"),
            "type": "ir.actions.act_window",
            "res_model": "wms.stock.transfer",
            "view_mode": "list,form",
            "domain": [("warehouse_id", "=", self.id)],
            "context": {"default_warehouse_id": self.id},
        }

    def action_view_shipments(self):
        self.ensure_one()
        return {
            "name": _("Shipments"),
            "type": "ir.actions.act_window",
            "res_model": "wms.stock.shipment",
            "view_mode": "list,form",
            "domain": [("warehouse_id", "=", self.id)],
            "context": {"default_warehouse_id": self.id},
        }
