from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WmsProduct(models.Model):
    _name = "wms.product"
    _description = "WMS Product"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(
        string="Product Name",
        required=True,
        tracking=True,
        help="Commercial or technical name of the product.",
    )
    sku = fields.Char(
        string="SKU",
        required=True,
        index=True,
        tracking=True,
        help="Stock Keeping Unit — unique alphanumeric product code.",
    )
    barcode = fields.Char(
        string="Barcode",
        index=True,
        copy=False,
        help="EAN-13, UPC, or internal barcode for barcode scanners.",
    )
    category = fields.Selection(
        selection=[
            ("electronics", "Electronics"),
            ("components", "Components & Parts"),
            ("peripherals", "Peripherals"),
            ("networking", "Networking"),
            ("furniture", "Office & Furniture"),
            ("other", "General Supplies"),
        ],
        string="Category",
        default="other",
        required=True,
        tracking=True,
    )
    unit_of_measure = fields.Selection(
        selection=[
            ("units", "Units (pcs)"),
            ("kg", "Kilograms (kg)"),
            ("m", "Meters (m)"),
            ("liters", "Liters (L)"),
            ("boxes", "Boxes (box)"),
        ],
        string="Unit of Measure",
        default="units",
        required=True,
    )
    minimum_stock = fields.Float(
        string="Minimum Stock",
        default=0.0,
        tracking=True,
        help="Threshold for low-stock warnings. If stock falls below this level, an alert is triggered.",
    )
    maximum_stock = fields.Float(
        string="Maximum Stock",
        default=0.0,
        help="Target maximum storage capacity for this item.",
    )
    stock_quantity = fields.Float(
        string="On Hand Stock",
        compute="_compute_stock_quantity",
        store=False,
        digits="Product Unit of Measure",
        help="Total available stock across all internal storage locations.",
    )
    is_low_stock = fields.Boolean(
        string="Low Stock Warning",
        compute="_compute_is_low_stock",
        search="_search_is_low_stock",
        help="True if on-hand quantity is less than the minimum stock threshold.",
    )
    weight = fields.Float(
        string="Weight (kg)",
        default=0.0,
        help="Gross weight per unit in kilograms.",
    )
    volume = fields.Float(
        string="Volume (m³)",
        default=0.0,
        help="Volume per unit in cubic meters.",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to archive the product. Archived products cannot be received or shipped.",
    )
    description = fields.Text(string="Description")

    _sql_constraints = [
        ("sku_unique", "UNIQUE(sku)", "SKU must be unique! Another product already has this SKU."),
        ("barcode_unique", "UNIQUE(barcode)", "Barcode must be unique! Another product has this barcode."),
    ]

    @api.constrains("minimum_stock", "maximum_stock")
    def _check_stock_levels(self):
        for product in self:
            if product.minimum_stock < 0:
                raise ValidationError(_("Minimum stock level cannot be negative."))
            if product.maximum_stock > 0 and product.maximum_stock < product.minimum_stock:
                raise ValidationError(
                    _("Maximum stock level (%(max)s) cannot be lower than minimum stock (%(min)s).",
                      max=product.maximum_stock, min=product.minimum_stock)
                )

    @api.constrains("weight", "volume")
    def _check_dimensions(self):
        for product in self:
            if product.weight < 0:
                raise ValidationError(_("Product weight cannot be negative."))
            if product.volume < 0:
                raise ValidationError(_("Product volume cannot be negative."))

    @api.constrains("sku")
    def _check_sku_not_empty(self):
        for product in self:
            if not product.sku or not product.sku.strip():
                raise ValidationError(_("Product SKU cannot be empty or blank."))

    def _compute_stock_quantity(self):
        """
        Computes the current on-hand stock quantity across all internal locations.
        Internal locations include: 'storage', 'receiving', 'shipping'.
        """
        for product in self:
            if "wms.stock.movement" in self.env:
                internal_types = ["storage", "receiving", "shipping", "damaged"]
                
                # Incoming: movements where destination is internal
                in_moves = self.env["wms.stock.movement"].search([
                    ("product_id", "=", product.id),
                    ("destination_location_id.location_type", "in", internal_types),
                ])
                qty_in = sum(in_moves.mapped("quantity"))

                # Outgoing: movements where source is internal
                out_moves = self.env["wms.stock.movement"].search([
                    ("product_id", "=", product.id),
                    ("source_location_id.location_type", "in", internal_types),
                ])
                qty_out = sum(out_moves.mapped("quantity"))

                product.stock_quantity = qty_in - qty_out
            else:
                product.stock_quantity = 0.0

    @api.depends("stock_quantity", "minimum_stock")
    def _compute_is_low_stock(self):
        for product in self:
            product.is_low_stock = bool(
                product.active
                and product.minimum_stock > 0
                and product.stock_quantity < product.minimum_stock
            )

    def _search_is_low_stock(self, operator, value):
        """
        Allows filtering products by is_low_stock in Search views.
        """
        if operator not in ("=", "!="):
            raise NotImplementedError(_("Operation not supported for is_low_stock search."))
        
        # Calculate matching products
        all_products = self.search([])
        matching_ids = []
        for p in all_products:
            is_low = bool(p.active and p.minimum_stock > 0 and p.stock_quantity < p.minimum_stock)
            if (is_low == value and operator == "=") or (is_low != value and operator == "!="):
                matching_ids.append(p.id)
        return [("id", "in", matching_ids)]

    def get_stock_in_location(self, location_id):
        """
        Helper method to get the available stock quantity of this product
        in a specific location.
        """
        self.ensure_one()
        if "wms.stock.movement" not in self.env:
            return 0.0

        # Inbound to this specific location
        in_moves = self.env["wms.stock.movement"].search([
            ("product_id", "=", self.id),
            ("destination_location_id", "=", location_id),
        ])
        qty_in = sum(in_moves.mapped("quantity"))

        # Outbound from this specific location
        out_moves = self.env["wms.stock.movement"].search([
            ("product_id", "=", self.id),
            ("source_location_id", "=", location_id),
        ])
        qty_out = sum(out_moves.mapped("quantity"))

        return qty_in - qty_out

    def check_and_create_low_stock_activity(self):
        """
        Automated action: Creates an Activity (task in chatter) for the warehouse manager
        or responsible user if the product stock is below minimum.
        """
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        for product in self:
            if product.is_low_stock:
                # Check if there is already an open low stock activity to avoid duplicates
                existing = self.env["mail.activity"].search([
                    ("res_model", "=", "wms.product"),
                    ("res_id", "=", product.id),
                    ("summary", "=", f"Low Stock Alert: {product.name}"),
                ], limit=1)
                if not existing:
                    product.activity_schedule(
                        activity_type_id=activity_type.id if activity_type else False,
                        summary=f"Low Stock Alert: {product.name}",
                        note=_(
                            "Product '%(name)s' (SKU: %(sku)s) is running low! "
                            "Current stock: %(qty)s %(uom)s, Minimum required: %(min)s %(uom)s. "
                            "Please initiate a Stock Receipt / Purchase order.",
                            name=product.name,
                            sku=product.sku,
                            qty=product.stock_quantity,
                            uom=product.unit_of_measure,
                            min=product.minimum_stock,
                        ),
                        user_id=self.env.user.id,
                    )
