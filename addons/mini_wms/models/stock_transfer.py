from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class WmsStockTransfer(models.Model):
    _name = "wms.stock.transfer"
    _description = "Internal Stock Transfer"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc, id desc"

    name = fields.Char(
        string="Transfer Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        comodel_name="wms.warehouse",
        string="Warehouse",
        required=True,
        tracking=True,
        domain="[('active', '=', True)]",
    )
    source_location_id = fields.Many2one(
        comodel_name="wms.location",
        string="Source Location",
        required=True,
        tracking=True,
        domain="[('warehouse_id', '=', warehouse_id), ('location_type', 'in', ['receiving', 'storage'])]",
        help="Location where products are currently stored.",
    )
    destination_location_id = fields.Many2one(
        comodel_name="wms.location",
        string="Destination Location",
        required=True,
        tracking=True,
        domain="[('warehouse_id', '=', warehouse_id), ('location_type', 'in', ['storage', 'shipping', 'damaged'])]",
        help="Target location to move products into.",
    )
    responsible_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    transfer_date = fields.Date(
        string="Transfer Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        comodel_name="wms.stock.transfer.line",
        inverse_name="transfer_id",
        string="Transfer Lines",
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
        for transfer in self:
            transfer.total_quantity = sum(transfer.line_ids.mapped("quantity"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.stock.transfer") or _("New")
        return super().create(vals_list)

    @api.constrains("source_location_id", "destination_location_id")
    def _check_locations_differ(self):
        for transfer in self:
            if transfer.source_location_id and transfer.destination_location_id:
                if transfer.source_location_id == transfer.destination_location_id:
                    raise ValidationError(_("Source location and Destination location cannot be the same!"))
                if transfer.source_location_id.warehouse_id != transfer.warehouse_id:
                    raise ValidationError(_("Source location must belong to the selected warehouse!"))
                if transfer.destination_location_id.warehouse_id != transfer.warehouse_id:
                    raise ValidationError(_("Destination location must belong to the selected warehouse!"))

    def action_confirm(self):
        for transfer in self:
            if transfer.state != "draft":
                raise UserError(_("Only draft transfers can be confirmed."))
            if not transfer.line_ids:
                raise UserError(_("Cannot confirm a transfer without products."))
            transfer.state = "confirmed"
            transfer.message_post(body=_("Transfer confirmed and ready for execution."))

    def action_done(self):
        """
        Executes the transfer:
        1. Validates available stock in source_location_id for each product
        2. Raises UserError if stock is insufficient
        3. Creates immutable stock movements
        4. Sets state to 'done'
        """
        for transfer in self:
            if transfer.state == "done":
                raise UserError(_("Transfer '%(name)s' is already done! Cannot execute again.", name=transfer.name))
            if transfer.state not in ("draft", "confirmed"):
                raise UserError(_("Only draft or confirmed transfers can be processed."))
            if not transfer.line_ids:
                raise UserError(_("Transfer has no lines to move."))
            if not transfer.warehouse_id.active:
                raise UserError(_("Cannot perform transfer in an archived warehouse!"))

            # Group requested quantity by product to handle duplicate lines gracefully
            product_requests = {}
            for line in transfer.line_ids:
                if not line.product_id.active:
                    raise UserError(_("Product '%(prod)s' is archived and cannot be moved.", prod=line.product_id.name))
                if line.quantity <= 0:
                    raise ValidationError(_("Quantity must be greater than 0 for product '%(prod)s'.", prod=line.product_id.name))
                product_requests[line.product_id] = product_requests.get(line.product_id, 0.0) + line.quantity

            # Validate stock availability in the source location
            for product, requested_qty in product_requests.items():
                available_qty = product.get_stock_in_location(transfer.source_location_id.id)
                if available_qty < requested_qty:
                    raise UserError(
                        _(
                            'Not enough stock for product "%(prod)s" in location "%(loc)s". '
                            "Available: %(avail)s, requested: %(req)s.",
                            prod=product.name,
                            loc=transfer.source_location_id.complete_name,
                            avail=available_qty,
                            req=requested_qty,
                        )
                    )

            # Create movements
            move_vals = []
            for line in transfer.line_ids:
                move_vals.append({
                    "product_id": line.product_id.id,
                    "quantity": line.quantity,
                    "source_location_id": transfer.source_location_id.id,
                    "destination_location_id": transfer.destination_location_id.id,
                    "operation_type": "transfer",
                    "reference": transfer.name,
                    "date": fields.Datetime.now(),
                    "responsible_user_id": transfer.responsible_user_id.id,
                })

            self.env["wms.stock.movement"].create(move_vals)
            transfer.state = "done"
            transfer.message_post(body=_(
                "Transfer completed. %(qty)s items moved from '%(src)s' to '%(dst)s'.",
                qty=transfer.total_quantity,
                src=transfer.source_location_id.complete_name,
                dst=transfer.destination_location_id.complete_name,
            ))

    def action_cancel(self):
        for transfer in self:
            if transfer.state == "done":
                raise UserError(_("Cannot cancel a completed transfer! Use a reverse transfer to return items."))
            transfer.state = "cancelled"
            transfer.message_post(body=_("Transfer cancelled."))

    def action_draft(self):
        for transfer in self:
            if transfer.state == "done":
                raise UserError(_("Cannot reset a completed transfer back to draft."))
            transfer.state = "draft"

    def unlink(self):
        for transfer in self:
            if transfer.state not in ("draft", "cancelled"):
                raise UserError(_("You can only delete draft or cancelled transfers!"))
        return super().unlink()


class WmsStockTransferLine(models.Model):
    _name = "wms.stock.transfer.line"
    _description = "Internal Stock Transfer Line"
    _order = "id"

    transfer_id = fields.Many2one(
        comodel_name="wms.stock.transfer",
        string="Stock Transfer",
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

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Transfer quantity must be strictly greater than 0!"))
