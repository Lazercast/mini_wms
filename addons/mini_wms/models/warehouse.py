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
        Computes the number of distinct products in stock within this warehouse.
        Once wms.stock.movement is created, it aggregates positive stock.
        """
        for warehouse in self:
            if "wms.stock.movement" in self.env:
                movements = self.env["wms.stock.movement"].search([
                    ("destination_location_id.warehouse_id", "=", warehouse.id),
                ])
                warehouse.product_count = len(movements.mapped("product_id"))
            else:
                warehouse.product_count = 0
