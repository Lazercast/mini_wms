from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class WmsStockReceipt(models.Model):
    _name = "wms.stock.receipt"
    _description = "Stock Receipt Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc, id desc"

    name = fields.Char(
        string="Receipt Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        comodel_name="wms.warehouse",
        string="Destination Warehouse",
        required=True,
        tracking=True,
        domain="[('active', '=', True)]",
    )
    source_supplier = fields.Char(
        string="Supplier / Vendor",
        required=True,
        tracking=True,
        help="Name of the supplier sending goods.",
    )
    receipt_date = fields.Date(
        string="Receipt Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    responsible_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("received", "Received"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        comodel_name="wms.stock.receipt.line",
        inverse_name="receipt_id",
        string="Receipt Lines",
        copy=True,
    )
    total_quantity = fields.Float(
        string="Total Quantity",
        compute="_compute_total_quantity",
        store=True,
    )
    notes = fields.Text(string="Notes")

    @api.depends("line_ids.quantity")
    def _compute_total_quantity(self):
        for receipt in self:
            receipt.total_quantity = sum(receipt.line_ids.mapped("quantity"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.stock.receipt") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for receipt in self:
            if receipt.state != "draft":
                raise UserError(_("Only draft receipts can be confirmed."))
            if not receipt.line_ids:
                raise UserError(_("Cannot confirm a receipt with no product lines!"))
            receipt.state = "confirmed"
            receipt.message_post(body=_("Receipt confirmed and waiting for physical arrival."))

    def action_receive(self):
        """
        Receives goods into warehouse:
        1. Validates lines and locations
        2. Posts immutable wms.stock.movement records
        3. Updates status to 'received'
        """
        for receipt in self:
            if receipt.state == "received":
                raise UserError(_("Receipt '%(name)s' has already been received! Double receipt is strictly forbidden.", name=receipt.name))
            if receipt.state not in ("draft", "confirmed"):
                raise UserError(_("Only draft or confirmed receipts can be processed."))
            if not receipt.line_ids:
                raise UserError(_("Cannot receive an empty order. Please add products."))
            if not receipt.warehouse_id.active:
                raise UserError(_("Cannot receive goods into an archived warehouse!"))

            # Create stock movement for each line
            move_vals = []
            for line in receipt.line_ids:
                if not line.product_id.active:
                    raise UserError(_("Cannot receive archived product '%(prod)s'!", prod=line.product_id.name))
                if line.quantity <= 0:
                    raise ValidationError(_("Received quantity must be strictly greater than 0 for product '%(prod)s'.", prod=line.product_id.name))
                if line.destination_location_id.warehouse_id != receipt.warehouse_id:
                    raise ValidationError(_("Destination location '%(loc)s' does not belong to warehouse '%(wh)s'.",
                                          loc=line.destination_location_id.complete_name,
                                          wh=receipt.warehouse_id.name))

                move_vals.append({
                    "product_id": line.product_id.id,
                    "quantity": line.quantity,
                    "source_location_id": False,  # External supplier
                    "destination_location_id": line.destination_location_id.id,
                    "operation_type": "receipt",
                    "reference": receipt.name,
                    "date": fields.Datetime.now(),
                    "responsible_user_id": receipt.responsible_user_id.id,
                })

            self.env["wms.stock.movement"].create(move_vals)
            receipt.state = "received"
            receipt.message_post(body=_("Goods physically received into warehouse locations. Stock movements posted."))

    def action_cancel(self):
        for receipt in self:
            if receipt.state == "received":
                raise UserError(_("Cannot cancel a receipt that has already been received! Use inventory adjustment to correct stock."))
            receipt.state = "cancelled"
            receipt.message_post(body=_("Receipt cancelled."))

    def action_draft(self):
        for receipt in self:
            if receipt.state == "received":
                raise UserError(_("Cannot reset a received order back to draft."))
            receipt.state = "draft"

    def unlink(self):
        for receipt in self:
            if receipt.state not in ("draft", "cancelled"):
                raise UserError(_("You can only delete draft or cancelled receipts!"))
        return super().unlink()


class WmsStockReceiptLine(models.Model):
    _name = "wms.stock.receipt.line"
    _description = "Stock Receipt Line"
    _order = "id"

    receipt_id = fields.Many2one(
        comodel_name="wms.stock.receipt",
        string="Stock Receipt",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        comodel_name="wms.product",
        string="Product",
        required=True,
        domain="[('active', '=', True)]",
    )
    quantity = fields.Float(
        string="Quantity",
        required=True,
        default=1.0,
        digits="Product Unit of Measure",
    )
    destination_location_id = fields.Many2one(
        comodel_name="wms.location",
        string="Destination Location",
        required=True,
        help="Bin or zone where goods will be placed.",
    )
    unit_price = fields.Float(
        string="Unit Price",
        default=0.0,
    )
    subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True,
    )

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Line quantity must be strictly greater than 0!"))

    @api.constrains("destination_location_id", "receipt_id")
    def _check_location_warehouse(self):
        for line in self:
            if line.receipt_id and line.destination_location_id:
                if line.destination_location_id.warehouse_id != line.receipt_id.warehouse_id:
                    raise ValidationError(
                        _(
                            "Destination location '%(loc)s' belongs to '%(loc_wh)s', "
                            "but this receipt is for warehouse '%(rc_wh)s'!",
                            loc=line.destination_location_id.complete_name,
                            loc_wh=line.destination_location_id.warehouse_id.name,
                            rc_wh=line.receipt_id.warehouse_id.name,
                        )
                    )
