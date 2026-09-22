from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WmsLocation(models.Model):
    _name = "wms.location"
    _description = "Warehouse Location"
    _order = "complete_name, id"
    _rec_name = "complete_name"

    name = fields.Char(
        string="Location Name",
        required=True,
        help="Name of the zone, shelf or bin (e.g. Storage A, Bin A-01).",
    )
    code = fields.Char(
        string="Location Code",
        required=True,
        help="Internal code for scanning or labeling (e.g. A-01, IN-01).",
    )
    warehouse_id = fields.Many2one(
        comodel_name="wms.warehouse",
        string="Warehouse",
        required=True,
        ondelete="cascade",
        index=True,
        help="The warehouse this location belongs to.",
    )
    parent_location_id = fields.Many2one(
        comodel_name="wms.location",
        string="Parent Location",
        ondelete="cascade",
        index=True,
        domain="[('warehouse_id', '=', warehouse_id)]",
        help="Parent zone or rack for hierarchical warehouse layouts.",
    )
    child_location_ids = fields.One2many(
        comodel_name="wms.location",
        inverse_name="parent_location_id",
        string="Sub-Locations",
    )
    complete_name = fields.Char(
        string="Full Location Path",
        compute="_compute_complete_name",
        recursive=True,
        store=True,
        help="Hierarchical name showing the full path (e.g. Storage A / A-01).",
    )
    location_type = fields.Selection(
        selection=[
            ("receiving", "Receiving Area"),
            ("storage", "Storage Zone"),
            ("shipping", "Shipping Area"),
            ("damaged", "Damaged / Quarantine"),
            ("inventory", "Inventory Adjustment Virtual Location"),
        ],
        string="Location Type",
        default="storage",
        required=True,
        help="Operational purpose of this location.",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to archive the location.",
    )

    _sql_constraints = [
        (
            "warehouse_code_unique",
            "UNIQUE(warehouse_id, code)",
            "Location code must be unique within the same warehouse!",
        ),
    ]

    @api.depends("name", "parent_location_id.complete_name")
    def _compute_complete_name(self):
        for location in self:
            if location.parent_location_id:
                location.complete_name = (
                    f"{location.parent_location_id.complete_name} / {location.name}"
                )
            else:
                location.complete_name = location.name

    @api.constrains("parent_location_id")
    def _check_parent_recursion(self):
        if not self._check_recursion():
            raise ValidationError(
                _("You cannot create recursive locations! A location cannot be its own parent.")
            )

    @api.constrains("warehouse_id", "parent_location_id")
    def _check_warehouse_consistency(self):
        for loc in self:
            if loc.parent_location_id and loc.parent_location_id.warehouse_id != loc.warehouse_id:
                raise ValidationError(
                    _(
                        "Parent location '%(parent)s' belongs to warehouse '%(parent_wh)s', "
                        "while child location '%(child)s' is assigned to '%(child_wh)s'. "
                        "Both must belong to the same warehouse!",
                        parent=loc.parent_location_id.name,
                        parent_wh=loc.parent_location_id.warehouse_id.name,
                        child=loc.name,
                        child_wh=loc.warehouse_id.name,
                    )
                )
