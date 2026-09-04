#!/usr/bin/env python3
"""
Trading Alert System.

Ticker-agnostic real-time monitor that generates audio alerts when the
configured 5-condition voter fires for the symbol passed on construction.
Originally written for IWM; the rules generalize to any liquid ETF/stock
covered by AlphaVantage's 1-min intraday endpoint.

Note: this is a Windows-only desktop tool — it imports ``winsound`` for
the audio cue. The cloud equivalent is ``gcp/signal_monitor.py``, which
runs as a Cloud Run job and writes to Cloud SQL ``signal_alerts``.
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
import json
import time as time_module
from typing import Dict, List, Tuple, Optional
import requests
from dataclasses import dataclass
from enum import Enum
import winsound  # For Windows alert sounds
import os

class SignalType(Enum):
    CALL = "CALL"
    PUT = "PUT"
    NONE = "NONE"

@dataclass
class TradingSignal:
    signal_type: SignalType
    entry_time: datetime
    price: float
    rsi: float
    rvol: float
    signal_strength: int
    conditions_met: List[str]
    target_price: float
    stop_price: float
    time_stop: int  # minutes

class TradingAlertSystem:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.current_data = {}
        self.alerts_fired = {}
        self.position = None
        
        # Trading parameters based on analysis
        self.params = {
            'prime_start': time(9, 30),
            'prime_end': time(10, 0),
            'good_end': time(14, 0),
            'close_time': time(16, 0),
            'call_target': 0.0030,  # 0.30%
            'put_target': 0.0038,   # 0.38%
            'call_stop': 0.0015,    # 0.15%
            'put_stop': 0.0020,     # 0.20%
            'call_time_stop': 30,   # minutes
            'put_time_stop': 35,    # minutes
            'min_rvol': 1.0,
            'strong_rvol': 1.5,
            'high_rvol': 3.0,
            'min_atr': 0.15,
            'high_atr': 0.20
        }
        
    def check_market_hours(self) -> bool:
        """Check if market is open"""
        now = datetime.now()
        current_time = now.time()
        
        # Check if weekend
        if now.weekday() >= 5:
            return False
            
        # Check if within market hours
        return time(9, 30) <= current_time <= time(16, 0)
    
    def get_time_period(self) -> str:
        """Determine current trading period"""
        current_time = datetime.now().time()
        
        if current_time < time(9, 30):
            return "pre-market"
        elif current_time >= self.params['prime_start'] and current_time <= self.params['prime_end']:
            return "prime"
        elif current_time > self.params['prime_end'] and current_time <= self.params['good_end']:
            return "good"
        elif current_time > self.params['good_end'] and current_time <= self.params['close_time']:
            return "avoid"
        else:
            return "closed"
    
    def calculate_signal_strength(self, conditions: List[bool]) -> Tuple[int, List[str]]:
        """Calculate signal strength based on conditions met"""
        condition_names = [
            "Contrarian VWAP", "RSI Range", "RVOL > 1.0", "Prime Time",
            "Strong RVOL", "EMA Alignment", "StochRSI Signal", "ATR High",
            "OBV Extreme", "Morning Session"
        ]
        
        met_conditions = []
        for i, condition in enumerate(conditions):
            if condition and i < len(condition_names):
                met_conditions.append(condition_names[i])
        
        return len(met_conditions), met_conditions
    
    def check_call_conditions(self, data: Dict) -> Tuple[bool, int, List[str]]:
        """Check conditions for CALL signal based on contrarian approach"""
        conditions = []
        
        # Minimum requirements
        min_req_1 = data['price'] < data['vwap']  # Contrarian
        min_req_2 = 45 < data['rsi'] < 70
        min_req_3 = data['rvol'] > self.params['min_rvol']
        
        if not all([min_req_1, min_req_2, min_req_3]):
            return False, 0, []
        
        # Strong setup conditions
        conditions.append(min_req_1)  # Contrarian VWAP
        conditions.append(min_req_2)  # RSI Range
        conditions.append(min_req_3)  # RVOL > 1.0
        conditions.append(self.get_time_period() == "prime")
        conditions.append(data['rvol'] > self.params['strong_rvol'])
        conditions.append(data['price'] < data['ema9'])
        conditions.append(data.get('stoch_rsi', 50) > 70)
        conditions.append(data.get('atr', 0) > self.params['min_atr'])
        conditions.append(data.get('obv_percentile', 50) < 20)
        conditions.append(datetime.now().time() <= time(10, 0))
        
        strength, met_conditions = self.calculate_signal_strength(conditions)
        
        # Need at least 3 strong conditions beyond minimum
        if strength >= 6:  # 3 minimum + 3 additional
            return True, strength, met_conditions
        
        return False, strength, met_conditions
    
    def check_put_conditions(self, data: Dict) -> Tuple[bool, int, List[str]]:
        """Check conditions for PUT signal based on contrarian approach"""
        conditions = []
        
        # Minimum requirements
        min_req_1 = data['price'] > data['vwap']  # Contrarian
        min_req_2 = 30 < data['rsi'] < 55
        min_req_3 = data['rvol'] > self.params['min_rvol']
        
        if not all([min_req_1, min_req_2, min_req_3]):
            return False, 0, []
        
        # Strong setup conditions
        conditions.append(min_req_1)  # Contrarian VWAP
        conditions.append(min_req_2)  # RSI Range
        conditions.append(min_req_3)  # RVOL > 1.0
        conditions.append(self.get_time_period() in ["prime", "good"])
        conditions.append(data['rvol'] > self.params['strong_rvol'])
        conditions.append(data['price'] > data['ema9'])
        conditions.append(data.get('stoch_rsi', 50) < 30)
        conditions.append(data.get('atr', 0) > self.params['min_atr'])
        conditions.append(data['rsi'] < 40)  # Stronger signal
        conditions.append(data['ema9'] < data['ema20'])
        
        strength, met_conditions = self.calculate_signal_strength(conditions)
        
        # Need at least 3 strong conditions beyond minimum
        if strength >= 6:  # 3 minimum + 3 additional
            return True, strength, met_conditions
        
        return False, strength, met_conditions
    
    def check_exit_conditions(self, signal: TradingSignal, current_data: Dict) -> Tuple[bool, str]:
        """Check if position should be exited"""
        if not signal:
            return False, ""
        
        current_price = current_data['price']
        entry_price = signal.price
        
        # Calculate return
        if signal.signal_type == SignalType.CALL:
            returns = (current_price - entry_price) / entry_price
        else:  # PUT
            returns = (entry_price - current_price) / entry_price
        
        # Time stop
        time_elapsed = (datetime.now() - signal.entry_time).seconds / 60
        if time_elapsed >= signal.time_stop:
            return True, f"Time stop: {time_elapsed:.0f} minutes"
        
        # Profit target
        if signal.signal_type == SignalType.CALL and returns >= self.params['call_target']:
            return True, f"Target hit: {returns:.2%}"
        elif signal.signal_type == SignalType.PUT and returns >= self.params['put_target']:
            return True, f"Target hit: {returns:.2%}"
        
        # Stop loss
        if signal.signal_type == SignalType.CALL and returns <= -self.params['call_stop']:
            return True, f"Stop hit: {returns:.2%}"
        elif signal.signal_type == SignalType.PUT and returns <= -self.params['put_stop']:
            return True, f"Stop hit: {returns:.2%}"
        
        # Extreme RSI exit
        if signal.signal_type == SignalType.CALL and current_data['rsi'] > 80:
            return True, f"RSI exit: {current_data['rsi']:.1f}"
        elif signal.signal_type == SignalType.PUT and current_data['rsi'] < 20:
            return True, f"RSI exit: {current_data['rsi']:.1f}"
        
        return False, ""
    
    def generate_alert(self, signal_type: str, data: Dict, strength: int, conditions: List[str]):
        """Generate and display alert"""
        alert_key = f"{signal_type}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
        # Prevent duplicate alerts
        if alert_key in self.alerts_fired:
            return
        
        self.alerts_fired[alert_key] = datetime.now()
        
        # Build alert message
        if signal_type == "CALL":
            emoji = "🟢"
            target = data['price'] * (1 + self.params['call_target'])
            stop = data['price'] * (1 - self.params['call_stop'])
        else:
            emoji = "🔴"
            target = data['price'] * (1 - self.params['put_target'])
            stop = data['price'] * (1 + self.params['put_stop'])
        
        message = f"""
{emoji} {signal_type} SETUP DETECTED {emoji}
========================
Time: {datetime.now().strftime('%H:%M:%S')}
Price: ${data['price']:.2f}
RSI: {data['rsi']:.1f}
RVOL: {data['rvol']:.2f}x
Signal Strength: {strength}/10

Target: ${target:.2f} ({self.params[f'{signal_type.lower()}_target']*100:.1%})
Stop: ${stop:.2f} ({self.params[f'{signal_type.lower()}_stop']*100:.1%})

Conditions Met:
{chr(10).join([f'✓ {c}' for c in conditions])}
========================
        """
        
        print(message)
        
        # Sound alert (Windows)
        if os.name == 'nt':
            winsound.Beep(1000 if signal_type == "CALL" else 500, 500)
        
        # Log alert
        self.log_alert(signal_type, data, strength, conditions)
    
    def log_alert(self, signal_type: str, data: Dict, strength: int, conditions: List[str]):
        """Log alert to file"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'signal_type': signal_type,
            'price': data['price'],
            'rsi': data['rsi'],
            'rvol': data['rvol'],
            'vwap': data['vwap'],
            'signal_strength': strength,
            'conditions': conditions
        }
        
        with open('trading_alerts_log.json', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def monitor_conditions(self, data: Dict):
        """Main monitoring function"""
        if not self.check_market_hours():
            return
        
        # Check for exit conditions first
        if self.position:
            should_exit, reason = self.check_exit_conditions(self.position, data)
            if should_exit:
                print(f"📤 EXIT SIGNAL: {reason}")
                self.position = None
                return
        
        # Check for new signals only if not in position
        if not self.position:
            # Check CALL conditions
            call_signal, call_strength, call_conditions = self.check_call_conditions(data)
            if call_signal:
                self.generate_alert("CALL", data, call_strength, call_conditions)
                self.position = TradingSignal(
                    signal_type=SignalType.CALL,
                    entry_time=datetime.now(),
                    price=data['price'],
                    rsi=data['rsi'],
                    rvol=data['rvol'],
                    signal_strength=call_strength,
                    conditions_met=call_conditions,
                    target_price=data['price'] * (1 + self.params['call_target']),
                    stop_price=data['price'] * (1 - self.params['call_stop']),
                    time_stop=self.params['call_time_stop']
                )
                return
            
            # Check PUT conditions
            put_signal, put_strength, put_conditions = self.check_put_conditions(data)
            if put_signal:
                self.generate_alert("PUT", data, put_strength, put_conditions)
                self.position = TradingSignal(
                    signal_type=SignalType.PUT,
                    entry_time=datetime.now(),
                    price=data['price'],
                    rsi=data['rsi'],
                    rvol=data['rvol'],
                    signal_strength=put_strength,
                    conditions_met=put_conditions,
                    target_price=data['price'] * (1 - self.params['put_target']),
                    stop_price=data['price'] * (1 + self.params['put_stop']),
                    time_stop=self.params['put_time_stop']
                )
        
        # Check for warning conditions
        period = self.get_time_period()
        if period == "avoid":
            print("⚠️ Warning: Avoid trading after 2 PM - lower probability")
        
        if data['rvol'] < 0.5:
            print("⚠️ Warning: Very low volume - avoid trading")
        
        if data.get('atr', 0.1) < 0.05:
            print("⚠️ Warning: Low volatility - smaller moves expected")

# Example usage
def main():
    # Initialize alert system
    alert_system = TradingAlertSystem()
    
    # Simulated data for testing
    test_data = {
        'price': 225.50,
        'vwap': 226.00,  # Price < VWAP for CALL (contrarian)
        'rsi': 55,
        'rvol': 2.1,
        'ema9': 226.10,
        'ema20': 226.30,
        'ema50': 227.00,
        'stoch_rsi': 75,
        'atr': 0.18,
        'obv_percentile': 15
    }
    
    print("Trading Alert System Started...")
    print(f"Current Time Period: {alert_system.get_time_period()}")
    print(f"Market Hours: {'OPEN' if alert_system.check_market_hours() else 'CLOSED'}")
    print("-" * 50)
    
    # Monitor conditions
    alert_system.monitor_conditions(test_data)

if __name__ == "__main__":
    main()