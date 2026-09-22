from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestWmsReceipt(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Warehouse = cls.env["wms.warehouse"]
        cls.Location = cls.env["wms.location"]
        cls.Product = cls.env["wms.product"]
        cls.Receipt = cls.env["wms.stock.receipt"]

        cls.warehouse = cls.Warehouse.create({
            "name": "Central Hub",
            "code": "WH-REC",
        })
        cls.loc_receiving = cls.Location.create({
            "name": "Dock 1",
            "code": "DCK-01",
            "warehouse_id": cls.warehouse.id,
            "location_type": "receiving",
        })
        cls.product = cls.Product.create({
            "name": "Industrial Router",
            "sku": "SKU-ROUTER-001",
            "minimum_stock": 5.0,
        })

    def test_01_create_receipt_sequence(self):
        """Test that new receipts get automatic REC sequence numbers."""
        receipt = self.Receipt.create({
            "warehouse_id": self.warehouse.id,
            "source_supplier": "Supplier Tech Ltd",
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 10.0,
                    "destination_location_id": self.loc_receiving.id,
                    "unit_price": 250.0,
                }),
            ],
        })
        self.assertTrue(receipt.name.startswith("REC"), "Reference should start with REC sequence prefix.")
        self.assertEqual(receipt.state, "draft")
        self.assertEqual(receipt.total_quantity, 10.0)
        self.assertEqual(receipt.line_ids[0].subtotal, 2500.0)

    def test_02_receive_increases_stock(self):
        """Test full receipt workflow from draft to received, verifying stock increase."""
        receipt = self.Receipt.create({
            "warehouse_id": self.warehouse.id,
            "source_supplier": "Supplier Tech Ltd",
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 8.0,
                    "destination_location_id": self.loc_receiving.id,
                    "unit_price": 250.0,
                }),
            ],
        })
        initial_stock = self.product.stock_quantity

        # Confirm and Receive
        receipt.action_confirm()
        self.assertEqual(receipt.state, "confirmed")

        receipt.action_receive()
        self.assertEqual(receipt.state, "received")

        # Verify stock and audit movement
        self.assertEqual(self.product.stock_quantity, initial_stock + 8.0)
        move = self.env["wms.stock.movement"].search([("reference", "=", receipt.name)])
        self.assertTrue(move, "Audit movement must be generated.")
        self.assertEqual(move.quantity, 8.0)
        self.assertEqual(move.operation_type, "receipt")

    def test_03_double_receive_error(self):
        """Test that an already received receipt cannot be received again."""
        receipt = self.Receipt.create({
            "warehouse_id": self.warehouse.id,
            "source_supplier": "Supplier Tech Ltd",
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 5.0,
                    "destination_location_id": self.loc_receiving.id,
                }),
            ],
        })
        receipt.action_confirm()
        receipt.action_receive()

        with self.assertRaises(UserError):
            receipt.action_receive()

    def test_04_invalid_receipt_line(self):
        """Test validation rules: quantity must be positive and location must match warehouse."""
        other_wh = self.Warehouse.create({"name": "Other WH", "code": "WH-OTHER"})
        other_loc = self.Location.create({
            "name": "Other Loc",
            "code": "OTH-01",
            "warehouse_id": other_wh.id,
            "location_type": "receiving",
        })

        # Test negative quantity
        with self.assertRaises(ValidationError):
            self.Receipt.create({
                "warehouse_id": self.warehouse.id,
                "source_supplier": "Bad Supplier",
                "line_ids": [
                    (0, 0, {
                        "product_id": self.product.id,
                        "quantity": -2.0,
                        "destination_location_id": self.loc_receiving.id,
                    }),
                ],
            })

        # Test mismatching warehouse location
        with self.assertRaises(ValidationError):
            self.Receipt.create({
                "warehouse_id": self.warehouse.id,
                "source_supplier": "Bad Supplier",
                "line_ids": [
                    (0, 0, {
                        "product_id": self.product.id,
                        "quantity": 5.0,
                        "destination_location_id": other_loc.id,
                    }),
                ],
            })
