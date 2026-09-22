# Mini WMS for Odoo 18 Community

[![Odoo Version](https://img.shields.io/badge/Odoo-18.0-714B67.svg?style=flat&logo=odoo)](https://www.odoo.com)
[![Python Version](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?style=flat&logo=python)](https://www.python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg?style=flat&logo=postgresql)](https://www.postgresql.org)
[![License: LGPL-3](https://img.shields.io/badge/License-LGPL--3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)

A modular, production-ready **Mini Warehouse Management System (WMS)** built for **Odoo 18 Community Edition**. Designed according to enterprise ERP best practices, this module implements an **immutable stock ledger pattern**, multi-warehouse hierarchical location management, automated document numbering, and real-time inventory validation.

---

## 📖 Table of Contents

- [Description](#description)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Data Model](#data-model)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage Workflow](#usage)
- [Testing](#testing)
- [Screenshots](#screenshots)
- [Future Improvements](#future-improvements)

---

## 📌 Description

**Mini WMS** is a standalone, lightweight ERP warehouse management module. Unlike simple CRUD tutorials, it models actual logistics flows: receiving shipments from vendors, internal bin-to-bin transfers with on-hand availability checks, outbound customer shipments, and physical count discrepancies via inventory adjustments.

All inventory quantities are derived from an immutable **Stock Movement Ledger** (`wms.stock.movement`), ensuring 100% auditability, zero data drift, and enterprise-grade transaction safety.

---

## 🚀 Features

* **Multi-Warehouse & Hierarchical Locations**:
  * Multi-facility support (central hubs, regional branches).
  * Unlimited tree depth for storage locations (`Warehouse ➔ Zone ➔ Rack ➔ Bin`).
  * Dedicated functional zones: `Receiving`, `Storage`, `Shipping`, `Damaged / Quarantine`, `Inventory Loss/Gain`.
* **Stock Movement Ledger**:
  * Double-entry movement audit trail recording every inbound, transfer, outbound, and adjustment event.
  * Prevention of retroactive tampering via ORM guards (`unlink` and `write` protection).
* **Automated Document Sequences**:
  * Native sequence numbering for all operations: `REC00001`, `TR00001`, `SHIP00001`, `ADJ00001`.
* **Real-time Stock Validation**:
  * Outbound transfers and shipments automatically check available stock at the specific source location.
  * Informative user-facing exceptions (`UserError`) on insufficient stock.
* **Low-Stock Triggers & Automated Activities**:
  * Dynamic calculation of on-hand quantity and low-stock warnings (`is_low_stock`).
  * Automated creation of Odoo `mail.activity` tasks for warehouse managers when safety stock thresholds are breached.
* **Role-Based Access Control (RBAC)**:
  * **WMS User**: View stock, create receipts, transfers, and shipments.
  * **WMS Manager**: Manage warehouses, configure zones, conduct inventory adjustments, cancel orders, view audit reports.
* **Modern Odoo 18 UI/UX**:
  * Clean Kanban views, List views with status badges, Form views with dynamic statusbars, and Chatter integration.
  * Smart Buttons on Warehouses and Products for instant 1-click drill-down navigation.

---

## 🛠️ Tech Stack

* **Platform**: [Odoo 18.0 Community Edition](https://github.com/odoo/odoo)
* **Language**: Python 3.10+
* **Database**: PostgreSQL 16
* **Frontend**: Odoo 18 Web Client (QWeb, XML, Bootstrap 5)
* **DevOps**: Docker & Docker Compose
* **Testing**: Odoo Python Testing Framework (`TransactionCase`)

---

## 🏛️ Architecture

The module adheres to clean modular Odoo architecture:

```text
mini_wms_project/
├── docker-compose.yml              # Odoo 18 + PostgreSQL 16 containerization
├── requirements.txt                # Python environment requirements
├── LICENSE                         # LGPL-3 License
├── README.md                       # Documentation
└── addons/
    └── mini_wms/
        ├── __init__.py
        ├── __manifest__.py         # App declaration, dependencies & asset loading
        ├── models/
        │   ├── warehouse.py        # wms.warehouse
        │   ├── location.py         # wms.location (self-referential hierarchy)
        │   ├── product.py          # wms.product (computed on-hand & low-stock)
        │   ├── stock_movement.py   # wms.stock.movement (audit ledger)
        │   ├── stock_receipt.py    # wms.stock.receipt & lines
        │   ├── stock_transfer.py   # wms.stock.transfer & lines
        │   ├── stock_shipment.py   # wms.stock.shipment & lines
        │   └── inventory_adjustment.py # wms.inventory.adjustment
        ├── security/
        │   ├── security.xml        # User / Manager security groups
        │   └── ir.model.access.csv # Model access rules (ACL)
        ├── data/
        │   └── ir_sequence_data.xml# Automated document numbering
        ├── views/                  # UI Views (Kanban, List, Form, Search, Menus)
        ├── demo/
        │   └── demo_data.xml       # Turnkey demo dataset for quick start
        └── tests/                  # Automated unit test suite
```

---

## 📊 Data Model

```text
Warehouse
   |
   └── Locations (Hierarchical Self-Relation)

Product
   |
   └── Stock Movements (Immutable Ledger)

Receipt (Inbound)
   |
   └── Receipt Lines ───> Product / Destination Location

Transfer (Internal)
   |
   └── Transfer Lines ───> Product (Source Loc ➔ Destination Loc)

Shipment (Outbound)
   |
   └── Shipment Lines ───> Product / Source Location

Inventory Adjustment (Reconcile)
   |
   └── Direct Product / Location Adjustment
```

---

## 💻 Installation

### Method 1: Quick Start via Docker (Recommended)

1. Clone this repository:
   ```bash
   git clone https://github.com/Lazercast/mini_wms.git
   cd mini_wms
   ```

2. Launch Odoo and PostgreSQL containers:
   ```bash
   docker compose up -d
   ```

3. Open your browser and navigate to:
   ```text
   http://localhost:8069
   ```

4. Create a new database and ensure you check **"Load demonstration data"** if you want to explore the turnkey demo dataset.
5. Navigate to **Apps**, remove the default `Apps` filter in the search bar, search for `Mini WMS`, and click **Activate**.

---

### Method 2: Manual / Existing Odoo Installation

1. Copy or symlink the `addons/mini_wms` folder into your Odoo `addons-path`:
   ```bash
   ln -s $(pwd)/addons/mini_wms /path/to/odoo/custom_addons/mini_wms
   ```
2. Update your `odoo.conf`:
   ```ini
   addons_path = /path/to/odoo/addons,/path/to/odoo/custom_addons
   ```
3. Restart your Odoo server and update the apps list in Developer Mode.
4. Install **Mini WMS**.

---

## ⚙️ Configuration

1. **User Rights**:
   * Navigate to **Settings ➔ Users & Companies ➔ Users**.
   * Under the **Warehouse Management (WMS)** category, assign either:
     * **User (Clerk / Operator)**
     * **Manager (Supervisor / Admin)**
2. **Initial Setup**:
   * If not using demo data, configure your primary warehouse under **WMS ➔ Warehouses**.
   * Create zones under **WMS ➔ Locations** (e.g., `Receiving`, `Storage`, `Shipping`).

---

## 📋 Usage Workflow

Follow this standard end-to-end WMS lifecycle:

```text
1. Create Warehouse ──────> Register company physical site (e.g. "Main Logistics Hub").
2. Create Locations ──────> Build structure ("Receiving Dock", "Storage Zone A / Rack 01").
3. Create Product ────────> Add item with SKU, Barcode, and Minimum Safety Stock threshold.
4. Receive Product ───────> Create Stock Receipt from vendor ➔ Click "Receive Goods".
5. Check Stock ───────────> Verify On-Hand quantity automatically updated via movement ledger.
6. Transfer Product ──────> Relocate items from Receiving to Storage Rack with real-time stock check.
7. Ship Product ──────────> Dispatch items to customer ➔ Stock decrements ➔ Low-stock activity triggers.
8. Movement History ──────> Inspect the immutable audit trail under Reports ➔ Stock Movements.
```

---

## 🧪 Testing

The module comes with a comprehensive automated test suite covering all critical business rules:
* Product creation, duplicate SKU constraint, dynamic low-stock calculation.
* Inbound receipts, stock increases, double-receive prevention.
* Internal transfers, location stock updates, insufficient stock exceptions.
* Outbound shipments and safety stock triggers.
* Physical inventory adjustments (handling surpluses and losses).

To run the automated tests:

### Running tests via Docker:
```bash
docker compose run --rm web odoo -i mini_wms --test-enable --stop-after-init
```

### Running tests locally:
```bash
odoo-bin -c /path/to/odoo.conf -i mini_wms --test-enable --stop-after-init
```

---

## 📷 Screenshots

### 1. WMS Interactive Dashboard
*(Warehouse overview with real-time metrics and operational counters)*
```text
[ Insert Screenshot: WMS Dashboard with Warehouse Kanban Cards ]
```

### 2. Product Catalog & Low-Stock Alerts
*(Product Kanban and form view displaying safety thresholds and low stock warning banners)*
```text
[ Insert Screenshot: Product List & Form View with Warning Ribbon ]
```

### 3. Stock Receipt Order
*(Receipt statusbar, line items, and stock posting button)*
```text
[ Insert Screenshot: Stock Receipt Form View ]
```

### 4. Internal Transfer with Stock Validation
*(Moving items between racks with instant stock checks)*
```text
[ Insert Screenshot: Stock Transfer Form View ]
```

### 5. Immutable Stock Movement Ledger
*(Full historical ledger with visual route arrows and operation badges)*
```text
[ Insert Screenshot: Stock Movements Audit View ]
```

---

## 🔮 Future Improvements

- [ ] Barcode / QR Code mobile scanning interface (HTML5 / ZXing).
- [ ] Integration with Odoo standard `purchase` and `sale` modules.
- [ ] Automated batch picking, wave picking, and packing slips.
- [ ] Multi-company isolation and inter-company transfers.
- [ ] Advanced valuation methods (FIFO / AVCO cost tracking).
- [ ] REST API / Webhooks for external logistics platform integration.

---

## 📄 License

This project is licensed under the **GNU Lesser General Public License v3.0 (LGPL-3)** — see the [LICENSE](LICENSE) file for details.
