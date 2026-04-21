"""Eagerly import every model so SQLAlchemy `metadata` is fully populated.

Each phase appends its imports as the models land.
"""

from pos_inventory.persistence.base import Base, metadata

# Foundational (Phase 2)
from pos_inventory.persistence.models.site import Site, Location  # noqa: F401
from pos_inventory.persistence.models.sku import Sku  # noqa: F401
from pos_inventory.persistence.models.vendor import Vendor  # noqa: F401
from pos_inventory.persistence.models.serial import Serial  # noqa: F401
from pos_inventory.persistence.models.lot import Lot  # noqa: F401
from pos_inventory.persistence.models.balance import Balance  # noqa: F401
from pos_inventory.persistence.models.ledger import Ledger  # noqa: F401
from pos_inventory.persistence.models.cost_layer import CostLayer  # noqa: F401
from pos_inventory.persistence.models.adjustment import Adjustment  # noqa: F401
from pos_inventory.persistence.models.audit_entry import AuditEntry  # noqa: F401
from pos_inventory.persistence.models.outbox_event import OutboxEvent  # noqa: F401

# US1 (Phase 3)
from pos_inventory.persistence.models.purchase_order import PurchaseOrder  # noqa: F401
from pos_inventory.persistence.models.purchase_order_line import PurchaseOrderLine  # noqa: F401
from pos_inventory.persistence.models.receipt import Receipt  # noqa: F401
from pos_inventory.persistence.models.receipt_line import ReceiptLine  # noqa: F401
from pos_inventory.persistence.models.receipt_serial import ReceiptSerial  # noqa: F401

# US3 (Phase 5)
from pos_inventory.persistence.models.customer_return import CustomerReturn  # noqa: F401
from pos_inventory.persistence.models.customer_return_line import CustomerReturnLine  # noqa: F401
from pos_inventory.persistence.models.vendor_rma import VendorRma  # noqa: F401
from pos_inventory.persistence.models.vendor_rma_line import VendorRmaLine  # noqa: F401

# US4 (Phase 6)
from pos_inventory.persistence.models.count_session import CountSession  # noqa: F401
from pos_inventory.persistence.models.count_session_snapshot import CountSessionSnapshot  # noqa: F401
from pos_inventory.persistence.models.count_assignment import CountAssignment  # noqa: F401
from pos_inventory.persistence.models.count_entry import CountEntry  # noqa: F401

# US5 (Phase 7)
from pos_inventory.persistence.models.transfer import Transfer  # noqa: F401
from pos_inventory.persistence.models.transfer_line import TransferLine  # noqa: F401
from pos_inventory.persistence.models.transfer_serial import TransferSerial  # noqa: F401

# Polish (Phase 8)
from pos_inventory.persistence.models.config import TenantConfig  # noqa: F401

__all__ = ["Base", "metadata"]
