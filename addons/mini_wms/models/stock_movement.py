from odoo import api, fields, models, _
from odoo.exceptions import UserError


class WmsStockMovement(models.Model):
    _name = "wms.stock.movement"
    _description = "Stock Movement Ledger"
    _order = "date desc, id desc"

    product_id = fields.Many2one(
        comodel_name="wms.product",
        string="Product",
        required=True,
        index=True,
        ondelete="restrict",
    )
    quantity = fields.Float(
        string="Quantity",
        required=True,
        digits="Product Unit of Measure",
    )
    source_location_id = fields.Many2one(
        comodel_name="wms.location",
        string="Source Location",
        index=True,
        ondelete="restrict",
        help="Location where goods are taken from (empty for supplier receipts).",
    )
    destination_location_id = fields.Many2one(
        comodel_name="wms.location",
        string="Destination Location",
        index=True,
        ondelete="restrict",
        help="Location where goods are moved to (empty for customer shipments).",
    )
    operation_type = fields.Selection(
        selection=[
            ("receipt", "Receipt (Inbound)"),
            ("transfer", "Internal Transfer"),
            ("shipment", "Shipment (Outbound)"),
            ("adjustment", "Inventory Adjustment"),
        ],
        string="Operation Type",
        required=True,
        index=True,
    )
    reference = fields.Char(
        string="Reference / Document",
        required=True,
        index=True,
        help="Source document code (e.g. REC00001, TR00002, SHIP00003, ADJ00001).",
    )
    date = fields.Datetime(
        string="Movement Date",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )
    responsible_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible User",
        default=lambda self: self.env.user,
        required=True,
    )

    def unlink(self):
        """
        Stock movements are immutable audit records and cannot be deleted.
        """
        raise UserError(_("Stock movements are permanent audit records and cannot be deleted!"))

    def write(self, vals):
        """
        Stock movements are immutable. Only reference can be amended by admin if needed.
        """
        critical_fields = {"product_id", "quantity", "source_location_id", "destination_location_id", "operation_type", "date"}
        if any(f in vals for f in critical_fields):
            raise UserError(_("Completed stock movements cannot be modified!"))
        return super().write(vals)
