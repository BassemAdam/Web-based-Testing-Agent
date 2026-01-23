"""
Metrics tracking module for measuring response time and token consumption per phase.

Phases tracked:
- Phase 1: Page Exploration & Test Plan Preparation
- Phase 2: Code Generation
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from threading import Lock

# Try to import streamlit for session state persistence
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False


@dataclass
class PhaseMetrics:
    """Metrics for a single phase execution."""
    phase_name: str
    start_time: float = 0.0
    end_time: float = 0.0
    response_time_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "phase_name": self.phase_name,
            "response_time_seconds": round(self.response_time_seconds, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "avg_response_time_per_call": round(
                self.response_time_seconds / self.llm_calls, 3
            ) if self.llm_calls > 0 else 0,
            "avg_tokens_per_call": round(
                self.total_tokens / self.llm_calls, 1
            ) if self.llm_calls > 0 else 0,
        }


# =============================================================================
# GLOBAL PERSISTENT METRICS STORAGE (with Streamlit session_state support)
# =============================================================================

def _get_empty_metrics() -> Dict:
    """Return an empty metrics dictionary."""
    return {
        "phases": {},
        "totals": {
            "total_response_time_seconds": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_llm_calls": 0,
            "avg_response_time_per_call": 0,
        }
    }


def _get_metrics_storage() -> Dict:
    """Get the metrics storage, using st.session_state if available."""
    if HAS_STREAMLIT:
        try:
            if "_global_metrics" not in st.session_state:
                st.session_state._global_metrics = _get_empty_metrics()
            return st.session_state._global_metrics
        except Exception:
            # Fallback if streamlit context not available
            pass
    
    # Fallback to module-level global
    global _GLOBAL_METRICS
    return _GLOBAL_METRICS


def _set_metrics_storage(metrics: Dict):
    """Set the metrics storage."""
    if HAS_STREAMLIT:
        try:
            st.session_state._global_metrics = metrics
            return
        except Exception:
            pass
    
    global _GLOBAL_METRICS
    _GLOBAL_METRICS = metrics


# Module-level fallback storage
_GLOBAL_METRICS: Dict = _get_empty_metrics()


def get_global_metrics() -> Dict:
    """Get the global persistent metrics dictionary."""
    metrics = _get_metrics_storage()
    print(f"[METRICS] Getting global metrics: {len(metrics.get('phases', {}))} phases")
    _print_global_metrics()
    return metrics.copy()


def _print_global_metrics():
    """Print the current state of global metrics to console."""
    metrics = _get_metrics_storage()
    print("=" * 60)
    print("[METRICS] GLOBAL METRICS STATE:")
    print("-" * 60)
    phases = metrics.get("phases", {})
    if phases:
        for name, data in phases.items():
            print(f"  📊 {name}:")
            print(f"      Time: {data.get('response_time_seconds', 0):.2f}s")
            print(f"      Prompt Tokens: {data.get('prompt_tokens', 0):,}")
            print(f"      Completion Tokens: {data.get('completion_tokens', 0):,}")
            print(f"      Total Tokens: {data.get('total_tokens', 0):,}")
            print(f"      LLM Calls: {data.get('llm_calls', 0)}")
    else:
        print("  (no phases recorded)")
    print("-" * 60)
    totals = metrics.get("totals", {})
    print(f"  📈 TOTALS:")
    print(f"      Total Time: {totals.get('total_response_time_seconds', 0):.2f}s")
    print(f"      Total Tokens: {totals.get('total_tokens', 0):,}")
    print(f"      Total LLM Calls: {totals.get('total_llm_calls', 0)}")
    print("=" * 60)


def clear_global_metrics():
    """Clear all global metrics."""
    _set_metrics_storage(_get_empty_metrics())
    print("[METRICS] ⚠️ CLEARED global metrics")
    _print_global_metrics()


def _recalculate_totals():
    """Recalculate totals from all phases."""
    metrics = _get_metrics_storage()
    phases = metrics["phases"]
    
    total_time = sum(p.get("response_time_seconds", 0) for p in phases.values())
    total_prompt = sum(p.get("prompt_tokens", 0) for p in phases.values())
    total_completion = sum(p.get("completion_tokens", 0) for p in phases.values())
    total_tokens = sum(p.get("total_tokens", 0) for p in phases.values())
    total_calls = sum(p.get("llm_calls", 0) for p in phases.values())
    
    metrics["totals"] = {
        "total_response_time_seconds": round(total_time, 3),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_tokens,
        "total_llm_calls": total_calls,
        "avg_response_time_per_call": round(total_time / total_calls, 3) if total_calls > 0 else 0,
    }
    
    _set_metrics_storage(metrics)


def save_phase_to_global(phase_name: str, phase_dict: Dict):
    """Save a completed phase to global storage and recalculate totals."""
    print(f"[METRICS] 💾 Saving phase '{phase_name}' to global storage...")
    
    metrics = _get_metrics_storage()
    metrics["phases"][phase_name] = phase_dict
    _set_metrics_storage(metrics)
    
    _recalculate_totals()
    
    print(f"[METRICS] ✅ Phase '{phase_name}' saved successfully")
    _print_global_metrics()


# =============================================================================
# METRICS TRACKER CLASS
# =============================================================================
class MetricsTracker:
    """
    Singleton tracker for collecting metrics across phases.
    
    Usage:
        tracker = get_metrics_tracker()
        tracker.start_phase("exploration")
        # ... do work, call LLM ...
        tracker.record_llm_call(prompt_tokens=100, completion_tokens=50)
        tracker.end_phase()
    """
    
    _instance: Optional["MetricsTracker"] = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._current_phase: Optional[PhaseMetrics] = None
        self._phase_lock = Lock()
    
    def reset(self):
        """Reset metrics tracker and clear global storage."""
        with self._phase_lock:
            print("[METRICS] 🔄 Resetting metrics tracker...")
            self._current_phase = None
            clear_global_metrics()
    
    def start_phase(self, phase_name: str):
        """Begin tracking a new phase."""
        with self._phase_lock:
            # End current phase if exists
            if self._current_phase:
                self._finalize_phase()
            
            self._current_phase = PhaseMetrics(
                phase_name=phase_name,
                start_time=time.time()
            )
            print(f"[METRICS] 🚀 Started phase: {phase_name}")
    
    def record_llm_call(
        self, 
        prompt_tokens: int = 0, 
        completion_tokens: int = 0, 
        total_tokens: int = 0
    ):
        """Record an LLM API call within the current phase."""
        with self._phase_lock:
            if self._current_phase:
                self._current_phase.llm_calls += 1
                self._current_phase.prompt_tokens += prompt_tokens
                self._current_phase.completion_tokens += completion_tokens
                self._current_phase.total_tokens += total_tokens if total_tokens else (prompt_tokens + completion_tokens)
                print(f"[METRICS] 📝 Recorded LLM call #{self._current_phase.llm_calls} in {self._current_phase.phase_name}: "
                      f"+{total_tokens} tokens (total: {self._current_phase.total_tokens})")
            else:
                print(f"[METRICS] ⚠️ WARNING: record_llm_call called but no active phase!")
    
    def _finalize_phase(self):
        """Internal: finalize and store the current phase to global storage."""
        if self._current_phase:
            self._current_phase.end_time = time.time()
            self._current_phase.response_time_seconds = (
                self._current_phase.end_time - self._current_phase.start_time
            )
            
            print(f"[METRICS] 🏁 Finalizing phase: {self._current_phase.phase_name}")
            print(f"[METRICS]    Duration: {self._current_phase.response_time_seconds:.2f}s")
            print(f"[METRICS]    Tokens: {self._current_phase.total_tokens}")
            print(f"[METRICS]    LLM Calls: {self._current_phase.llm_calls}")
            
            # Save to global persistent storage
            phase_dict = self._current_phase.to_dict()
            save_phase_to_global(self._current_phase.phase_name, phase_dict)
            
            self._current_phase = None

    def end_phase(self) -> Optional[Dict]:
        """End the current phase and return global metrics."""
        with self._phase_lock:
            if self._current_phase:
                self._finalize_phase()
                return get_global_metrics()
            print(f"[METRICS] ⚠️ WARNING: end_phase called but no active phase!")
        return None
    
    def get_metrics(self) -> Dict:
        """Get all metrics from global storage."""
        return get_global_metrics()
    
    def get_current_phase_name(self) -> Optional[str]:
        """Get name of current active phase."""
        return self._current_phase.phase_name if self._current_phase else None
    
    def __str__(self) -> str:
        """Return a formatted string of all phase metrics."""
        metrics = get_global_metrics()
        phases = metrics.get("phases", {})
        
        lines = ["[METRICS] Session Summary:"]
        for name, phase_data in phases.items():
            lines.append(
                f"  - {name}: {phase_data.get('response_time_seconds', 0):.2f}s, "
                f"{phase_data.get('total_tokens', 0)} tokens, {phase_data.get('llm_calls', 0)} calls"
            )
        if not phases:
            lines.append("  (no phases recorded)")
        return "\n".join(lines)


# Global instance accessor
def get_metrics_tracker() -> MetricsTracker:
    """Get the global metrics tracker instance."""
    return MetricsTracker()


# Phase name constants
PHASE_EXPLORATION = "Phase 1: Exploration & Test Plan"
PHASE_CODE_GENERATION = "Phase 2: Code Generation"