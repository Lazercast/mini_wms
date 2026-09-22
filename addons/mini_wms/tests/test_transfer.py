from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestWmsTransfer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Warehouse = cls.env["wms.warehouse"]
        cls.Location = cls.env["wms.location"]
        cls.Product = cls.env["wms.product"]
        cls.Transfer = cls.env["wms.stock.transfer"]
        cls.Movement = cls.env["wms.stock.movement"]

        cls.warehouse = cls.Warehouse.create({
            "name": "Transfer Hub",
            "code": "WH-TR",
        })
        cls.loc_receiving = cls.Location.create({
            "name": "Receiving Bay",
            "code": "REC-01",
            "warehouse_id": cls.warehouse.id,
            "location_type": "receiving",
        })
        cls.loc_storage = cls.Location.create({
            "name": "Shelf A1",
            "code": "SHF-A1",
            "warehouse_id": cls.warehouse.id,
            "location_type": "storage",
        })
        cls.product = cls.Product.create({
            "name": "Server Blade",
            "sku": "SKU-SRV-001",
        })

    def test_01_successful_transfer(self):
        """Test moving stock between locations decreases source and increases destination."""
        # Initial stock: 10 units in receiving
        self.Movement.create({
            "product_id": self.product.id,
            "quantity": 10.0,
            "source_location_id": False,
            "destination_location_id": self.loc_receiving.id,
            "operation_type": "receipt",
            "reference": "INIT-001",
        })

        transfer = self.Transfer.create({
            "warehouse_id": self.warehouse.id,
            "source_location_id": self.loc_receiving.id,
            "destination_location_id": self.loc_storage.id,
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 6.0,
                }),
            ],
        })
        self.assertTrue(transfer.name.startswith("TR"))

        transfer.action_confirm()
        transfer.action_done()
        self.assertEqual(transfer.state, "done")

        # Check stock in both locations
        qty_in_receiving = self.product.get_stock_in_location(self.loc_receiving.id)
        qty_in_storage = self.product.get_stock_in_location(self.loc_storage.id)

        self.assertEqual(qty_in_receiving, 4.0, "Receiving stock should decrease from 10 to 4.")
        self.assertEqual(qty_in_storage, 6.0, "Storage stock should increase from 0 to 6.")
        self.assertEqual(self.product.stock_quantity, 10.0, "Total on-hand stock must remain 10.0.")

    def test_02_insufficient_stock_transfer_error(self):
        """Test that transferring more stock than available raises UserError."""
        # Available is only 2 in receiving
        self.Movement.create({
            "product_id": self.product.id,
            "quantity": 2.0,
            "source_location_id": False,
            "destination_location_id": self.loc_receiving.id,
            "operation_type": "receipt",
            "reference": "INIT-002",
        })

        transfer = self.Transfer.create({
            "warehouse_id": self.warehouse.id,
            "source_location_id": self.loc_receiving.id,
            "destination_location_id": self.loc_storage.id,
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 5.0,  # Requesting 5 when only 2 available
                }),
            ],
        })

        with self.assertRaises(UserError):
            transfer.action_done()

    def test_03_same_source_and_destination_error(self):
        """Test that source and destination locations cannot be identical."""
        with self.assertRaises(ValidationError):
            self.Transfer.create({
                "warehouse_id": self.warehouse.id,
                "source_location_id": self.loc_storage.id,
                "destination_location_id": self.loc_storage.id,
                "line_ids": [
                    (0, 0, {
                        "product_id": self.product.id,
                        "quantity": 1.0,
                    }),
                ],
            })
