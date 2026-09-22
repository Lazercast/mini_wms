from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class WmsStockShipment(models.Model):
    _name = "wms.stock.shipment"
    _description = "Stock Shipment Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc, id desc"

    name = fields.Char(
        string="Shipment Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        comodel_name="wms.warehouse",
        string="Source Warehouse",
        required=True,
        tracking=True,
        domain="[('active', '=', True)]",
    )
    customer = fields.Char(
        string="Customer",
        required=True,
        tracking=True,
        help="Client or destination organization receiving the shipment.",
    )
    shipping_date = fields.Date(
        string="Shipping Date",
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
            ("shipped", "Shipped"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        comodel_name="wms.stock.shipment.line",
        inverse_name="shipment_id",
        string="Shipment Lines",
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
        for shipment in self:
            shipment.total_quantity = sum(shipment.line_ids.mapped("quantity"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.stock.shipment") or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for shipment in self:
            if shipment.state != "draft":
                raise UserError(_("Only draft shipments can be confirmed."))
            if not shipment.line_ids:
                raise UserError(_("Cannot confirm a shipment with no products."))
            shipment.state = "confirmed"
            shipment.message_post(body=_("Shipment confirmed and queued for dispatch."))

    def action_ship(self):
        """
        Processes the outbound shipment:
        1. Validates available stock in the specified source location
        2. Raises UserError if stock is insufficient
        3. Creates immutable wms.stock.movement records
        4. Sets state to 'shipped'
        5. Triggers low-stock automated activities if threshold is breached
        """
        for shipment in self:
            if shipment.state == "shipped":
                raise UserError(_("Shipment '%(name)s' has already been shipped! Double shipping is forbidden.", name=shipment.name))
            if shipment.state not in ("draft", "confirmed"):
                raise UserError(_("Only draft or confirmed shipments can be dispatched."))
            if not shipment.line_ids:
                raise UserError(_("Cannot dispatch an empty shipment."))
            if not shipment.warehouse_id.active:
                raise UserError(_("Cannot ship from an archived warehouse!"))

            # Group requested quantity by (product, source_location) to validate accurately
            demand_map = {}
            for line in shipment.line_ids:
                if not line.product_id.active:
                    raise UserError(_("Product '%(prod)s' is archived and cannot be shipped.", prod=line.product_id.name))
                if line.quantity <= 0:
                    raise ValidationError(_("Shipped quantity must be strictly greater than 0 for '%(prod)s'.", prod=line.product_id.name))
                
                key = (line.product_id, line.source_location_id)
                demand_map[key] = demand_map.get(key, 0.0) + line.quantity

            # Check stock for each product in its source location
            for (product, location), req_qty in demand_map.items():
                available = product.get_stock_in_location(location.id)
                if available < req_qty:
                    raise UserError(
                        _(
                            'Not enough stock to ship product "%(prod)s" from location "%(loc)s". '
                            "Available: %(avail)s, requested: %(req)s.",
                            prod=product.name,
                            loc=location.complete_name,
                            avail=available,
                            req=req_qty,
                        )
                    )

            # Create outbound stock movements
            move_vals = []
            shipped_products = self.env["wms.product"]
            for line in shipment.line_ids:
                move_vals.append({
                    "product_id": line.product_id.id,
                    "quantity": line.quantity,
                    "source_location_id": line.source_location_id.id,
                    "destination_location_id": False,  # Customer
                    "operation_type": "shipment",
                    "reference": shipment.name,
                    "date": fields.Datetime.now(),
                    "responsible_user_id": shipment.responsible_user_id.id,
                })
                shipped_products |= line.product_id

            self.env["wms.stock.movement"].create(move_vals)
            shipment.state = "shipped"
            shipment.message_post(body=_(
                "Shipment dispatched to customer '%(cust)s'. %(qty)s items shipped.",
                cust=shipment.customer,
                qty=shipment.total_quantity,
            ))

            # Automated Action: Check if any product needs low-stock activity
            shipped_products.check_and_create_low_stock_activity()

    def action_cancel(self):
        for shipment in self:
            if shipment.state == "shipped":
                raise UserError(_("Cannot cancel a dispatched shipment! Create a return receipt instead."))
            shipment.state = "cancelled"
            shipment.message_post(body=_("Shipment cancelled."))

    def action_draft(self):
        for shipment in self:
            if shipment.state == "shipped":
                raise UserError(_("Cannot reset a shipped order back to draft."))
            shipment.state = "draft"

    def unlink(self):
        for shipment in self:
            if shipment.state not in ("draft", "cancelled"):
                raise UserError(_("You can only delete draft or cancelled shipments!"))
        return super().unlink()


class WmsStockShipmentLine(models.Model):
    _name = "wms.stock.shipment.line"
    _description = "Stock Shipment Line"
    _order = "id"

    shipment_id = fields.Many2one(
        comodel_name="wms.stock.shipment",
        string="Stock Shipment",
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
    source_location_id = fields.Many2one(
        comodel_name="wms.location",
        string="Source Location",
        required=True,
        help="Bin or area from which items are picked.",
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
                raise ValidationError(_("Shipment line quantity must be strictly greater than 0!"))

    @api.constrains("source_location_id", "shipment_id")
    def _check_location_warehouse(self):
        for line in self:
            if line.shipment_id and line.source_location_id:
                if line.source_location_id.warehouse_id != line.shipment_id.warehouse_id:
                    raise ValidationError(
                        _(
                            "Source location '%(loc)s' belongs to '%(loc_wh)s', "
                            "but shipment is from warehouse '%(sh_wh)s'!",
                            loc=line.source_location_id.complete_name,
                            loc_wh=line.source_location_id.warehouse_id.name,
                            sh_wh=line.shipment_id.warehouse_id.name,
                        )
                    )
