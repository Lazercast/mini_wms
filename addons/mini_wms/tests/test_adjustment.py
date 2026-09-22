from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestWmsAdjustment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Warehouse = cls.env["wms.warehouse"]
        cls.Location = cls.env["wms.location"]
        cls.Product = cls.env["wms.product"]
        cls.Adjustment = cls.env["wms.inventory.adjustment"]
        cls.Movement = cls.env["wms.stock.movement"]

        cls.warehouse = cls.Warehouse.create({
            "name": "Audit Warehouse",
            "code": "WH-AUD",
        })
        cls.loc_storage = cls.Location.create({
            "name": "Rack C1",
            "code": "RCK-C1",
            "warehouse_id": cls.warehouse.id,
            "location_type": "storage",
        })
        cls.product = cls.Product.create({
            "name": "Headphones Audio-Technica",
            "sku": "SKU-HDP-001",
            "minimum_stock": 5.0,
        })

    def test_01_positive_adjustment_gain(self):
        """Test physical count finding unrecorded items (gain)."""
        # Initial stock is 0
        self.assertEqual(self.product.get_stock_in_location(self.loc_storage.id), 0.0)

        # Audit finds 5 units physically present
        adj = self.Adjustment.create({
            "warehouse_id": self.warehouse.id,
            "location_id": self.loc_storage.id,
            "product_id": self.product.id,
            "actual_quantity": 5.0,
            "reason": "Found during annual audit",
        })
        self.assertTrue(adj.name.startswith("ADJ"))
        self.assertEqual(adj.system_quantity, 0.0)
        self.assertEqual(adj.difference_quantity, 5.0)

        adj.action_apply()
        self.assertEqual(adj.state, "applied")

        # Verify stock increased
        new_stock = self.product.get_stock_in_location(self.loc_storage.id)
        self.assertEqual(new_stock, 5.0, "Stock should be updated to 5.0.")

        # Check movement
        move = self.Movement.search([("reference", "=", adj.name)])
        self.assertTrue(move)
        self.assertEqual(move.quantity, 5.0)
        self.assertEqual(move.destination_location_id.id, self.loc_storage.id)
        self.assertFalse(move.source_location_id)

    def test_02_negative_adjustment_loss(self):
        """Test physical count finding missing or damaged items (loss)."""
        # Initial stock: 10 units
        self.Movement.create({
            "product_id": self.product.id,
            "quantity": 10.0,
            "source_location_id": False,
            "destination_location_id": self.loc_storage.id,
            "operation_type": "receipt",
            "reference": "INIT-HDP",
        })
        self.assertEqual(self.product.get_stock_in_location(self.loc_storage.id), 10.0)

        # Audit finds only 7 units (3 missing)
        adj = self.Adjustment.create({
            "warehouse_id": self.warehouse.id,
            "location_id": self.loc_storage.id,
            "product_id": self.product.id,
            "actual_quantity": 7.0,
            "reason": "Damaged goods discarded",
        })
        self.assertEqual(adj.system_quantity, 10.0)
        self.assertEqual(adj.difference_quantity, -3.0)

        adj.action_apply()
        self.assertEqual(adj.state, "applied")

        # Verify stock reduced to 7.0
        new_stock = self.product.get_stock_in_location(self.loc_storage.id)
        self.assertEqual(new_stock, 7.0, "Stock should be reduced to 7.0.")

        # Check movement
        move = self.Movement.search([("reference", "=", adj.name)])
        self.assertTrue(move)
        self.assertEqual(move.quantity, 3.0)
        self.assertEqual(move.source_location_id.id, self.loc_storage.id)
        self.assertFalse(move.destination_location_id)

    def test_03_negative_actual_quantity_error(self):
        """Test that actual physical quantity cannot be negative."""
        with self.assertRaises(ValidationError):
            self.Adjustment.create({
                "warehouse_id": self.warehouse.id,
                "location_id": self.loc_storage.id,
                "product_id": self.product.id,
                "actual_quantity": -5.0,
                "reason": "Impossible count",
            })
