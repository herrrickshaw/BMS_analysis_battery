"""
strategy.py
===========
Main strategy loop: scans all three instruments for put-call parity
deviations, enters trades when signals exceed the cost-adjusted threshold,
monitors open positions, and exits on profit target or stop-loss.

Run:
    python -m put_call_parity.strategy
or import and call Strategy().run() from main.py.
"""

import logging
import time
from datetime import date, datetime
from typing import Dict, List, Optional

from .broker import BrokerBase, get_broker
from .config import (
    BROKER,
    INSTRUMENTS,
    LOG_FILE,
    MAX_DTE,
    MAX_OPEN_POSITIONS,
    MIN_DTE,
    MIN_OI_THRESHOLD,
    RISK_FREE_RATE,
    SCAN_INTERVAL_SECONDS,
)
from .parity_engine import ParityEngine, ParitySignal
from .trade_manager import PositionBook, TradeManager

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Expiry helpers
# ---------------------------------------------------------------------------
def _nearest_expiries(broker: BrokerBase, instrument_key: str) -> List[str]:
    """Return sorted list of valid expiry strings (YYYY-MM-DD) for the instrument."""
    cfg = INSTRUMENTS[instrument_key]
    instruments = broker.kite.instruments(cfg.segment) if hasattr(broker, "kite") else []
    seen = set()
    expiries = []
    for inst in instruments:
        if inst.get("name") != cfg.option_symbol:
            continue
        exp = inst["expiry"]
        if hasattr(exp, "strftime"):
            exp_str = exp.strftime("%Y-%m-%d")
        else:
            exp_str = str(exp)
        if exp_str in seen:
            continue
        seen.add(exp_str)
        dte = (datetime.strptime(exp_str, "%Y-%m-%d").date() - date.today()).days
        if MIN_DTE <= dte <= MAX_DTE:
            expiries.append(exp_str)
    expiries.sort()
    return expiries


def _get_futures_quote(broker: BrokerBase, instrument_key: str, expiry: str) -> Optional[float]:
    """Fetch current mid-price of the front-month futures contract."""
    cfg = INSTRUMENTS[instrument_key]
    # Construct tradingsymbol for futures  (e.g. BANKNIFTY24JAN52000 pattern differs by broker)
    # Use instrument lookup from broker as the canonical source
    try:
        instruments = broker.kite.instruments(cfg.segment) if hasattr(broker, "kite") else []
        fut_list = [
            i for i in instruments
            if i.get("name") == cfg.futures_symbol
            and i.get("instrument_type") in ("FUT",)
            and (i["expiry"].strftime("%Y-%m-%d") if hasattr(i["expiry"], "strftime") else str(i["expiry"])) == expiry
        ]
        if not fut_list:
            return None
        sym = f"{cfg.segment}:{fut_list[0]['tradingsymbol']}"
        q = broker.get_quote([sym])
        data = q.get(sym, {})
        bid = (data.get("depth") or {}).get("buy", [{}])[0].get("price", 0)
        ask = (data.get("depth") or {}).get("sell", [{}])[0].get("price", 0)
        if bid and ask:
            return (bid + ask) / 2
        return data.get("last_price")
    except Exception as exc:
        log.warning("Failed to fetch futures quote for %s %s: %s", instrument_key, expiry, exc)
        return None


def _get_futures_symbol(broker: BrokerBase, instrument_key: str, expiry: str) -> str:
    cfg = INSTRUMENTS[instrument_key]
    try:
        instruments = broker.kite.instruments(cfg.segment) if hasattr(broker, "kite") else []
        fut_list = [
            i for i in instruments
            if i.get("name") == cfg.futures_symbol
            and i.get("instrument_type") == "FUT"
            and (i["expiry"].strftime("%Y-%m-%d") if hasattr(i["expiry"], "strftime") else str(i["expiry"])) == expiry
        ]
        if fut_list:
            return fut_list[0]["tradingsymbol"]
    except Exception:
        pass
    return cfg.futures_symbol


# ---------------------------------------------------------------------------
# Live quote refresh for open positions
# ---------------------------------------------------------------------------
def _refresh_option_prices(broker: BrokerBase, position: Dict) -> Dict[str, float]:
    """
    Fetch current bid/ask for both option legs of an open position.
    Returns dict with call_bid, call_ask, put_bid, put_ask.
    """
    segment = position["segment"]
    syms = [
        f"{segment}:{position['call_symbol']}",
        f"{segment}:{position['put_symbol']}",
    ]
    try:
        quotes = broker.get_quote(syms)
    except Exception as exc:
        log.warning("Quote refresh failed: %s", exc)
        return {}

    prices = {}
    for key, sym in [("call", syms[0]), ("put", syms[1])]:
        q = quotes.get(sym, {})
        depth = q.get("depth", {})
        prices[f"{key}_bid"] = (depth.get("buy", [{}])[0].get("price", 0) or q.get("last_price", 0))
        prices[f"{key}_ask"] = (depth.get("sell", [{}])[0].get("price", 0) or q.get("last_price", 0))
    return prices


# ---------------------------------------------------------------------------
# Strategy class
# ---------------------------------------------------------------------------
class Strategy:
    def __init__(self, broker: Optional[BrokerBase] = None):
        self.broker = broker or get_broker(BROKER)
        self.engine = ParityEngine(r=RISK_FREE_RATE)
        self.book   = PositionBook()
        self.tm     = TradeManager(self.broker, self.book)

    # -----------------------------------------------------------------------
    # Scan loop
    # -----------------------------------------------------------------------
    def _scan_instrument(self, instrument_key: str) -> List[ParitySignal]:
        cfg = INSTRUMENTS[instrument_key]
        expiries = _nearest_expiries(self.broker, instrument_key)
        if not expiries:
            log.warning("%s: no valid expiries in DTE window [%d, %d]", instrument_key, MIN_DTE, MAX_DTE)
            return []

        all_signals: List[ParitySignal] = []
        for expiry in expiries:
            futures_price = _get_futures_quote(self.broker, instrument_key, expiry)
            if not futures_price:
                log.warning("%s %s: could not get futures price — skipping", instrument_key, expiry)
                continue

            futures_symbol = _get_futures_symbol(self.broker, instrument_key, expiry)

            try:
                chain = self.broker.get_option_chain(cfg.option_symbol, expiry, cfg.segment)
            except Exception as exc:
                log.error("%s %s: option chain fetch failed: %s", instrument_key, expiry, exc)
                continue

            if not chain:
                continue

            signals = self.engine.scan(
                instrument_key=instrument_key,
                option_chain=chain,
                futures_price=futures_price,
                futures_symbol=futures_symbol,
                expiry=expiry,
                min_oi=MIN_OI_THRESHOLD,
            )
            log.info(
                "%s %s: futures=%.2f  chain_size=%d  signals=%d",
                instrument_key, expiry, futures_price, len(chain), len(signals),
            )
            all_signals.extend(signals)

        all_signals.sort(key=lambda s: s.net_deviation, reverse=True)
        return all_signals

    # -----------------------------------------------------------------------
    # Monitor open positions
    # -----------------------------------------------------------------------
    def _monitor_positions(self):
        positions = self.book.get_all()
        if not positions:
            return

        for pid, pos in list(positions.items()):
            cfg = INSTRUMENTS[pos["instrument"]]
            # Refresh option quotes
            opt_prices = _refresh_option_prices(self.broker, pos)
            if not opt_prices:
                continue

            # Refresh futures price
            fut_price = _get_futures_quote(self.broker, pos["instrument"], pos["expiry"])
            if not fut_price:
                continue

            # Build a minimal ParitySignal for the check_exit call
            signal = ParitySignal(
                instrument=pos["instrument"],
                expiry=pos["expiry"],
                strike=pos["strike"],
                dte=self.engine._dte(pos["expiry"]),
                futures_price=fut_price,
                call_mid=(opt_prices.get("call_bid", 0) + opt_prices.get("call_ask", 0)) / 2,
                put_mid=(opt_prices.get("put_bid", 0) + opt_prices.get("put_ask", 0)) / 2,
                call_symbol=pos["call_symbol"],
                put_symbol=pos["put_symbol"],
                futures_symbol=pos["futures_symbol"],
                theoretical_spread=0,
                observed_spread=0,
                raw_deviation=0,
                transaction_cost=0,
                net_deviation=0,
                direction=pos["direction"],
                lots=pos["lots"],
            )

            should_exit, reason = self.engine.check_exit(
                signal=signal,
                current_call_bid=opt_prices.get("call_bid", 0),
                current_call_ask=opt_prices.get("call_ask", 0),
                current_put_bid=opt_prices.get("put_bid", 0),
                current_put_ask=opt_prices.get("put_ask", 0),
                current_futures=fut_price,
                entry_deviation=pos["entry_deviation"],
                exit_fraction=cfg.exit_fraction,
                stop_loss_multiple=cfg.stop_loss_multiple,
            )

            if should_exit:
                log.info("Exit triggered for %s: %s", pid, reason)
                self.tm.exit_trade(pid, reason)

    # -----------------------------------------------------------------------
    # Main run loop
    # -----------------------------------------------------------------------
    def run(self):
        log.info("=" * 60)
        log.info("Put-Call Parity Arbitrage Strategy starting")
        log.info("Instruments: %s", list(INSTRUMENTS))
        log.info("Scan interval: %ds  |  Max positions: %d", SCAN_INTERVAL_SECONDS, MAX_OPEN_POSITIONS)
        log.info("=" * 60)

        while True:
            try:
                iteration_start = time.time()

                # 1. Monitor and exit open positions first
                self._monitor_positions()

                # 2. Scan for new opportunities (only if room for more positions)
                open_count = len(self.book)
                if open_count >= MAX_OPEN_POSITIONS:
                    log.info("Max positions (%d) reached — skipping scan", MAX_OPEN_POSITIONS)
                else:
                    all_signals: List[ParitySignal] = []
                    for key in INSTRUMENTS:
                        signals = self._scan_instrument(key)
                        all_signals.extend(signals)

                    # Sort globally by net deviation
                    all_signals.sort(key=lambda s: s.net_deviation, reverse=True)

                    slots = MAX_OPEN_POSITIONS - open_count
                    for signal in all_signals[:slots]:
                        log.info(
                            "Signal: %s %s K=%.0f  dir=%s  dev=%.2f (net=%.2f)",
                            signal.instrument, signal.expiry, signal.strike,
                            signal.direction, signal.raw_deviation, signal.net_deviation,
                        )
                        # Avoid duplicate positions on same instrument+expiry+strike
                        already_open = any(
                            p["instrument"] == signal.instrument
                            and p["expiry"] == signal.expiry
                            and p["strike"] == signal.strike
                            for p in self.book.get_all().values()
                        )
                        if already_open:
                            log.info("  Already have position on this strike — skipping")
                            continue

                        pid = self.tm.enter_trade(signal)
                        if pid:
                            log.info("  Entered -> position_id: %s", pid)

                elapsed = time.time() - iteration_start
                sleep_time = max(0, SCAN_INTERVAL_SECONDS - elapsed)
                log.debug("Iteration done in %.1fs, sleeping %.1fs", elapsed, sleep_time)
                time.sleep(sleep_time)

            except KeyboardInterrupt:
                log.info("Interrupted — shutting down gracefully")
                break
            except Exception as exc:
                log.exception("Unhandled error in main loop: %s", exc)
                time.sleep(5)   # brief pause before retrying
