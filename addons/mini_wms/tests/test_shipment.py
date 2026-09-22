from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestWmsShipment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Warehouse = cls.env["wms.warehouse"]
        cls.Location = cls.env["wms.location"]
        cls.Product = cls.env["wms.product"]
        cls.Shipment = cls.env["wms.stock.shipment"]
        cls.Movement = cls.env["wms.stock.movement"]

        cls.warehouse = cls.Warehouse.create({
            "name": "Outbound Center",
            "code": "WH-OUT",
        })
        cls.loc_shipping = cls.Location.create({
            "name": "Lane 1",
            "code": "LANE-01",
            "warehouse_id": cls.warehouse.id,
            "location_type": "shipping",
        })
        cls.product = cls.Product.create({
            "name": "Laser Printer",
            "sku": "SKU-PRN-001",
            "minimum_stock": 2.0,
        })

    def test_01_successful_shipment(self):
        """Test full shipment dispatch decreases on-hand stock."""
        # Initial stock: 5 units in shipping lane
        self.Movement.create({
            "product_id": self.product.id,
            "quantity": 5.0,
            "source_location_id": False,
            "destination_location_id": self.loc_shipping.id,
            "operation_type": "receipt",
            "reference": "INIT-PRN",
        })
        self.assertEqual(self.product.stock_quantity, 5.0)

        shipment = self.Shipment.create({
            "warehouse_id": self.warehouse.id,
            "customer": "Corporate Client CJSC",
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "source_location_id": self.loc_shipping.id,
                    "quantity": 3.0,
                }),
            ],
        })
        self.assertTrue(shipment.name.startswith("SHIP"))

        shipment.action_confirm()
        shipment.action_ship()
        self.assertEqual(shipment.state, "shipped")

        # Stock should be reduced to 2.0
        self.assertEqual(self.product.stock_quantity, 2.0)
        self.assertEqual(self.product.get_stock_in_location(self.loc_shipping.id), 2.0)

        # Check outbound movement created
        out_move = self.Movement.search([("reference", "=", shipment.name)])
        self.assertTrue(out_move)
        self.assertEqual(out_move.quantity, 3.0)
        self.assertFalse(out_move.destination_location_id, "Destination must be False (Customer).")

    def test_02_insufficient_stock_shipment_error(self):
        """Test that shipping more than available stock raises UserError."""
        # Only 1 available
        self.Movement.create({
            "product_id": self.product.id,
            "quantity": 1.0,
            "source_location_id": False,
            "destination_location_id": self.loc_shipping.id,
            "operation_type": "receipt",
            "reference": "INIT-LOW",
        })

        shipment = self.Shipment.create({
            "warehouse_id": self.warehouse.id,
            "customer": "Client XYZ",
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "source_location_id": self.loc_shipping.id,
                    "quantity": 10.0,
                }),
            ],
        })

        with self.assertRaises(UserError):
            shipment.action_ship()

    def test_03_double_shipment_error(self):
        """Test that a dispatched shipment cannot be shipped a second time."""
        self.Movement.create({
            "product_id": self.product.id,
            "quantity": 5.0,
            "source_location_id": False,
            "destination_location_id": self.loc_shipping.id,
            "operation_type": "receipt",
            "reference": "INIT-DBL",
        })

        shipment = self.Shipment.create({
            "warehouse_id": self.warehouse.id,
            "customer": "Client ABC",
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "source_location_id": self.loc_shipping.id,
                    "quantity": 2.0,
                }),
            ],
        })
        shipment.action_confirm()
        shipment.action_ship()

        with self.assertRaises(UserError):
            shipment.action_ship()
