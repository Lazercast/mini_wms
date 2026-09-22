from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class WmsInventoryAdjustment(models.Model):
    _name = "wms.inventory.adjustment"
    _description = "Inventory Adjustment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, name desc, id desc"

    name = fields.Char(
        string="Adjustment Reference",
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
    location_id = fields.Many2one(
        comodel_name="wms.location",
        string="Location",
        required=True,
        tracking=True,
        domain="[('warehouse_id', '=', warehouse_id), ('location_type', 'in', ['storage', 'receiving', 'shipping', 'damaged'])]",
        help="The physical zone or bin being audited.",
    )
    product_id = fields.Many2one(
        comodel_name="wms.product",
        string="Product",
        required=True,
        tracking=True,
        domain="[('active', '=', True)]",
    )
    system_quantity = fields.Float(
        string="System Quantity",
        compute="_compute_system_quantity",
        store=True,
        readonly=False,
        digits="Product Unit of Measure",
        help="On-hand quantity recorded in the system before physical check.",
    )
    actual_quantity = fields.Float(
        string="Actual Counted Quantity",
        required=True,
        default=0.0,
        tracking=True,
        digits="Product Unit of Measure",
        help="Physical count observed during inventory audit.",
    )
    difference_quantity = fields.Float(
        string="Discrepancy (Diff)",
        compute="_compute_difference_quantity",
        store=True,
        digits="Product Unit of Measure",
        help="Difference = Actual Quantity - System Quantity (+ is surplus, - is loss).",
    )
    reason = fields.Char(
        string="Reason for Discrepancy",
        required=True,
        tracking=True,
        help="Explanation (e.g. Damaged during handling, Annual audit, Found unrecorded stock).",
    )
    responsible_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Auditor / Responsible",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string="Adjustment Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("applied", "Applied"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    notes = fields.Text(string="Notes")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.inventory.adjustment") or _("New")
        return super().create(vals_list)

    @api.depends("product_id", "location_id")
    def _compute_system_quantity(self):
        for adj in self:
            if adj.product_id and adj.location_id:
                adj.system_quantity = adj.product_id.get_stock_in_location(adj.location_id.id)
            else:
                adj.system_quantity = 0.0

    @api.onchange("product_id", "location_id")
    def _onchange_product_location(self):
        if self.product_id and self.location_id:
            current_stock = self.product_id.get_stock_in_location(self.location_id.id)
            self.system_quantity = current_stock
            self.actual_quantity = current_stock

    @api.depends("actual_quantity", "system_quantity")
    def _compute_difference_quantity(self):
        for adj in self:
            adj.difference_quantity = adj.actual_quantity - adj.system_quantity

    @api.constrains("actual_quantity")
    def _check_actual_quantity(self):
        for adj in self:
            if adj.actual_quantity < 0:
                raise ValidationError(_("Actual physical quantity cannot be negative!"))

    @api.constrains("location_id", "warehouse_id")
    def _check_location_warehouse(self):
        for adj in self:
            if adj.location_id and adj.warehouse_id:
                if adj.location_id.warehouse_id != adj.warehouse_id:
                    raise ValidationError(_("Location '%(loc)s' does not belong to warehouse '%(wh)s'.",
                                          loc=adj.location_id.complete_name,
                                          wh=adj.warehouse_id.name))

    def action_apply(self):
        """
        Applies inventory adjustment:
        - If diff > 0: stock gain (incoming movement into location_id)
        - If diff < 0: stock loss (outgoing movement from location_id)
        - If diff == 0: no movement needed, simply marks as applied
        """
        for adj in self:
            if adj.state == "applied":
                raise UserError(_("Adjustment '%(name)s' has already been applied!", name=adj.name))
            if adj.state == "cancelled":
                raise UserError(_("Cannot apply a cancelled adjustment."))
            if not adj.product_id.active:
                raise UserError(_("Cannot adjust stock for archived product '%(prod)s'.", prod=adj.product_id.name))
            if not adj.warehouse_id.active:
                raise UserError(_("Cannot perform adjustments in an archived warehouse."))

            diff = adj.difference_quantity
            if diff > 0:
                # Gain: virtual -> location_id
                self.env["wms.stock.movement"].create({
                    "product_id": adj.product_id.id,
                    "quantity": diff,
                    "source_location_id": False,
                    "destination_location_id": adj.location_id.id,
                    "operation_type": "adjustment",
                    "reference": adj.name,
                    "date": fields.Datetime.now(),
                    "responsible_user_id": adj.responsible_user_id.id,
                })
            elif diff < 0:
                # Loss: location_id -> virtual
                self.env["wms.stock.movement"].create({
                    "product_id": adj.product_id.id,
                    "quantity": abs(diff),
                    "source_location_id": adj.location_id.id,
                    "destination_location_id": False,
                    "operation_type": "adjustment",
                    "reference": adj.name,
                    "date": fields.Datetime.now(),
                    "responsible_user_id": adj.responsible_user_id.id,
                })

            adj.state = "applied"
            adj.message_post(body=_(
                "Inventory adjustment applied. System quantity was: %(sys)s, actual count: %(act)s. "
                "Discrepancy of %(diff)s recorded. Reason: %(reason)s",
                sys=adj.system_quantity,
                act=adj.actual_quantity,
                diff=diff,
                reason=adj.reason,
            ))

            # Trigger low stock check if quantity was reduced
            if diff < 0:
                adj.product_id.check_and_create_low_stock_activity()

    def action_cancel(self):
        for adj in self:
            if adj.state == "applied":
                raise UserError(_("Cannot cancel an applied inventory adjustment! Create a new adjustment to correct it."))
            adj.state = "cancelled"
            adj.message_post(body=_("Adjustment cancelled."))

    def action_draft(self):
        for adj in self:
            if adj.state == "applied":
                raise UserError(_("Cannot reset an applied adjustment back to draft."))
            adj.state = "draft"

    def unlink(self):
        for adj in self:
            if adj.state not in ("draft", "cancelled"):
                raise UserError(_("You can only delete draft or cancelled adjustments!"))
        return super().unlink()
