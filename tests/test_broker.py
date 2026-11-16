import unittest

from pia_runtime.broker import (
    BrokerCapability,
    BrokerCapabilityDisabled,
    OrderRequest,
    PaperBrokerAdapter,
)


class PaperBrokerTest(unittest.TestCase):
    def test_capabilities_are_read_only_and_paper_only(self):
        broker = PaperBrokerAdapter()

        self.assertIn(BrokerCapability.PREVIEW_ORDER, broker.capabilities())
        self.assertIn(BrokerCapability.PAPER_SUBMIT, broker.capabilities())
        self.assertNotIn(BrokerCapability.LIVE_SUBMIT, broker.capabilities())

        with self.assertRaises(BrokerCapabilityDisabled):
            broker.submit_order(OrderRequest("600000.SH", "BUY", 100))

    def test_preview_and_paper_receipt_are_recorded(self):
        broker = PaperBrokerAdapter()
        portfolio = {"cash": 1000, "total_value": 1000, "quality": "verified"}
        request = OrderRequest(
            symbol="600000.sh",
            side="buy",
            quantity=100,
            limit_price=8,
            client_order_id="demo-order",
        )

        preview = broker.preview_order(request, portfolio=portfolio)
        self.assertEqual(preview["status"], "PREVIEW")
        self.assertEqual(preview["request"]["symbol"], "600000.SH")
        self.assertEqual(preview["estimated_value"], 800)
        self.assertEqual(preview["warnings"], [])

        receipt = broker.paper_submit(request, portfolio=portfolio)
        self.assertEqual(receipt.status, "PAPER_ACCEPTED")
        self.assertEqual(receipt.order_id, "demo-order")
        self.assertEqual(len(broker.get_orders()), 1)


if __name__ == "__main__":
    unittest.main()
