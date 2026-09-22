from odoo import api, fields, models, _
from odoo.exceptions import UserError


class WmsStockMovement(models.Model):
    _name = "wms.stock.movement"
    _description = "Stock Movement Ledger"
    _order = "date desc, id desc"
    _rec_name = "display_name"

    product_id = fields.Many2one(
        comodel_name="wms.product",
        string="Product",
        required=True,
        index=True,
        ondelete="restrict",
    )
    product_uom = fields.Selection(
        related="product_id.unit_of_measure",
        string="Unit of Measure",
        readonly=True,
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
        help="Source location (empty for external supplier receipts).",
    )
    destination_location_id = fields.Many2one(
        comodel_name="wms.location",
        string="Destination Location",
        index=True,
        ondelete="restrict",
        help="Destination location (empty for outbound customer shipments).",
    )
    source_warehouse_id = fields.Many2one(
        comodel_name="wms.warehouse",
        related="source_location_id.warehouse_id",
        string="Source Warehouse",
        store=True,
        index=True,
    )
    destination_warehouse_id = fields.Many2one(
        comodel_name="wms.warehouse",
        related="destination_location_id.warehouse_id",
        string="Destination Warehouse",
        store=True,
        index=True,
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
        string="Document Reference",
        required=True,
        index=True,
        help="Source document reference code (e.g. REC00001, TR00001, SHIP00001, ADJ00001).",
    )
    date = fields.Datetime(
        string="Date & Time",
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
    route_display = fields.Char(
        string="Movement Route",
        compute="_compute_route_display",
        store=True,
        help="Visual representation of the goods flow.",
    )
    display_name = fields.Char(
        string="Movement Title",
        compute="_compute_display_name",
        store=True,
    )

    @api.depends("source_location_id.complete_name", "destination_location_id.complete_name", "operation_type")
    def _compute_route_display(self):
        for move in self:
            src = move.source_location_id.complete_name if move.source_location_id else _("External / Supplier")
            dst = move.destination_location_id.complete_name if move.destination_location_id else _("External / Customer")
            move.route_display = f"{src} ➔ {dst}"

    @api.depends("reference", "product_id.name", "quantity", "product_uom")
    def _compute_display_name(self):
        for move in self:
            move.display_name = (
                f"[{move.reference}] {move.product_id.name or _('Item')} "
                f"({move.quantity} {move.product_uom or ''})"
            )

    def unlink(self):
        """
        Movements form the legal/audit ledger of the warehouse and cannot be deleted.
        """
        raise UserError(_("Stock movements are permanent audit records and cannot be deleted!"))

    def write(self, vals):
        """
        Movements are strictly immutable once created.
        """
        critical = {"product_id", "quantity", "source_location_id", "destination_location_id", "operation_type", "date"}
        if any(field in vals for field in critical):
            raise UserError(_("Stock movements are immutable and cannot be altered!"))
        return super().write(vals)
