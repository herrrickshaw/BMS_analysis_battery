"""
application/ports/report_writer.py
====================================
Output Port (interface) — implemented by Infrastructure.

A "Port" in Hexagonal Architecture (Ports & Adapters) is an interface the
Application layer needs. The Infrastructure layer provides "Adapters" that
implement the port.

IReportWriter is an OUTPUT port (Application drives it).
IStockRepository is an INPUT/data port (Application is driven by data needs).

Implementations live in infrastructure/reporting/:
  - ExcelReportWriter   — writes .xlsx workbooks (openpyxl)
  - HtmlEmailWriter     — generates and sends HTML email reports
  - CompositeWriter     — writes Excel AND emails in one call
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List


class IReportWriter(ABC):
    """Contract for writing scan results to an output format."""

    @abstractmethod
    def write(
        self,
        stocks:           Dict,           # {symbol: Stock}
        screener_results: Dict[str, int], # {screener_name: count}
        triple_hits:      List[str],
        multi_hits:       List[str],
        regime:           str,
        vix:              float,
    ) -> str:
        """Write the report and return the output path (or message-id for email)."""
        ...


class INotificationService(ABC):
    """
    Output port for external notifications (email, Slack, push).
    Decouples Application from Gmail/SMTP/Slack APIs.
    """

    @abstractmethod
    def send_email(self, to: str, subject: str, html_body: str) -> bool:
        """Send an HTML email. Returns True on success."""
        ...

    @abstractmethod
    def send_alert(self, channel: str, message: str) -> bool:
        """Send a real-time alert (e.g. intraday breakout to Slack/push)."""
        ...
