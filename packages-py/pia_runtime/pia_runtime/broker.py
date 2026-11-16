from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class BrokerCapability:
    READ_PORTFOLIO = "READ_PORTFOLIO"
    READ_BALANCE = "READ_BALANCE"
    READ_ORDERS = "READ_ORDERS"
    PREVIEW_ORDER = "PREVIEW_ORDER"
    PAPER_SUBMIT = "PAPER_SUBMIT"
    LIVE_SUBMIT = "LIVE_SUBMIT"


class BrokerCapabilityDisabled(RuntimeError):
    code = "CAPABILITY_DISABLED"


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: str
    quantity: float
    limit_price: float | None = None
    client_order_id: str | None = None

    def normalized(self) -> "OrderRequest":
        symbol = self.symbol.strip().upper()
        side = self.side.strip().upper()
        quantity = float(self.quantity)
        if not symbol:
            raise ValueError("order symbol is required")
        if side not in {"BUY", "SELL"}:
            raise ValueError("order side must be BUY or SELL")
        if quantity <= 0:
            raise ValueError("order quantity must be positive")
        if self.limit_price is not None and float(self.limit_price) <= 0:
            raise ValueError("limit price must be positive")
        return OrderRequest(
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=float(self.limit_price) if self.limit_price is not None else None,
            client_order_id=self.client_order_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "client_order_id": self.client_order_id,
        }


@dataclass(slots=True)
class PaperOrderReceipt:
    order_id: str
    status: str
    request: dict[str, Any]
    created_at: str
    provider_id: str = "paper"
    fill_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "status": self.status,
            "request": self.request,
            "created_at": self.created_at,
            "provider_id": self.provider_id,
            "fill_price": self.fill_price,
        }


@dataclass(slots=True)
class PaperBrokerAdapter:
    """Read-only and paper-order adapter; it never writes to a live broker."""

    provider_id: str = "paper"
    _orders: list[PaperOrderReceipt] = field(default_factory=list)
    _sequence: int = 0

    def capabilities(self) -> set[str]:
        return {
            BrokerCapability.READ_PORTFOLIO,
            BrokerCapability.READ_BALANCE,
            BrokerCapability.READ_ORDERS,
            BrokerCapability.PREVIEW_ORDER,
            BrokerCapability.PAPER_SUBMIT,
        }

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": "healthy",
            "capabilities": sorted(self.capabilities()),
            "live_submit_enabled": False,
        }

    def get_portfolio(self, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        if snapshot is None:
            return {
                "source": self.provider_id,
                "quality": "unavailable",
                "positions": [],
                "cash": 0.0,
                "total_value": 0.0,
            }
        return {
            **snapshot,
            "source": snapshot.get("source", self.provider_id),
        }

    def get_balance(self, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        portfolio = self.get_portfolio(snapshot)
        return {
            "cash": float(portfolio.get("cash", 0) or 0),
            "total_value": float(portfolio.get("total_value", 0) or 0),
            "source": portfolio.get("source", self.provider_id),
            "quality": portfolio.get("quality", "partial"),
        }

    def get_orders(self) -> list[dict[str, Any]]:
        return [order.to_dict() for order in self._orders]

    def preview_order(
        self,
        order: OrderRequest,
        *,
        portfolio: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = order.normalized()
        balance = self.get_balance(portfolio)
        estimated_value = (
            request.quantity * request.limit_price
            if request.limit_price is not None
            else None
        )
        warnings: list[str] = []
        if request.side == "BUY" and estimated_value is not None and estimated_value > balance["cash"]:
            warnings.append("INSUFFICIENT_PAPER_CASH")
        return {
            "status": "PREVIEW",
            "provider_id": self.provider_id,
            "request": request.to_dict(),
            "estimated_value": estimated_value,
            "warnings": warnings,
            "live_submit_enabled": False,
        }

    def paper_submit(
        self,
        order: OrderRequest,
        *,
        portfolio: dict[str, Any] | None = None,
    ) -> PaperOrderReceipt:
        preview = self.preview_order(order, portfolio=portfolio)
        self._sequence += 1
        request = order.normalized()
        receipt = PaperOrderReceipt(
            order_id=request.client_order_id or f"paper_{self._sequence:06d}",
            status="PAPER_ACCEPTED",
            request=request.to_dict(),
            created_at=datetime.now(timezone.utc).isoformat(),
            fill_price=request.limit_price,
        )
        self._orders.append(receipt)
        return receipt

    def submit_order(self, order: OrderRequest) -> PaperOrderReceipt:
        raise BrokerCapabilityDisabled(
            "Live broker submission is disabled; use preview_order or paper_submit."
        )
