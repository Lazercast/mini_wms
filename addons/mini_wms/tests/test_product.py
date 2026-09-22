from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger
import psycopg2


class TestWmsProduct(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Product = cls.env["wms.product"]
        cls.Warehouse = cls.env["wms.warehouse"]
        cls.Location = cls.env["wms.location"]
        cls.Movement = cls.env["wms.stock.movement"]

        # Base warehouse and location
        cls.warehouse = cls.Warehouse.create({
            "name": "Test WH",
            "code": "WH-TEST",
        })
        cls.loc_storage = cls.Location.create({
            "name": "Bin 01",
            "code": "BIN-01",
            "warehouse_id": cls.warehouse.id,
            "location_type": "storage",
        })

    def test_01_create_product(self):
        """Test successful product creation with default values."""
        product = self.Product.create({
            "name": "Test Laptop",
            "sku": "SKU-TEST-001",
            "category": "electronics",
            "unit_of_measure": "units",
            "minimum_stock": 5.0,
            "maximum_stock": 50.0,
            "weight": 2.0,
            "volume": 0.01,
        })
        self.assertTrue(product.id, "Product should be saved with a valid ID.")
        self.assertEqual(product.stock_quantity, 0.0, "Initial on-hand stock should be 0.0.")
        self.assertTrue(product.is_low_stock, "Product should be flagged as low stock since 0 < 5.")

    def test_02_duplicate_sku_error(self):
        """Test that duplicate SKU triggers integrity error."""
        self.Product.create({
            "name": "First Item",
            "sku": "SKU-UNIQUE-001",
        })
        with mute_logger("odoo.sql_db"), self.assertRaises(psycopg2.IntegrityError):
            self.Product.create({
                "name": "Second Item with Same SKU",
                "sku": "SKU-UNIQUE-001",
            })

    def test_03_low_stock_calculation(self):
        """Test dynamic calculation of is_low_stock based on stock movements."""
        product = self.Product.create({
            "name": "Test Mouse",
            "sku": "SKU-MOUSE-001",
            "minimum_stock": 10.0,
        })
        self.assertTrue(product.is_low_stock, "Should be low stock initially (0 < 10).")

        # Simulate receiving 15 units into storage
        self.Movement.create({
            "product_id": product.id,
            "quantity": 15.0,
            "source_location_id": False,
            "destination_location_id": self.loc_storage.id,
            "operation_type": "receipt",
            "reference": "TEST-REC-001",
        })

        self.assertEqual(product.stock_quantity, 15.0, "Stock quantity should be 15.0.")
        self.assertFalse(product.is_low_stock, "Should no longer be low stock (15 >= 10).")

    def test_04_invalid_stock_thresholds(self):
        """Test validation constraints on minimum and maximum stock levels."""
        with self.assertRaises(ValidationError):
            self.Product.create({
                "name": "Invalid Thresholds",
                "sku": "SKU-BAD-001",
                "minimum_stock": -5.0,
            })

        with self.assertRaises(ValidationError):
            self.Product.create({
                "name": "Max Lower Than Min",
                "sku": "SKU-BAD-002",
                "minimum_stock": 20.0,
                "maximum_stock": 10.0,
            })
